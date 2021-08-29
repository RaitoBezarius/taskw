import logging
import os
import shutil

from taskw.fields import (
    ChoiceField,
    DateField,
    DurationField,
    NumericField,
    StringField
)


logger = logging.getLogger(__name__)


def sanitize(line):
    comment_position = line.find('#')
    if comment_position < 0:
        return line.strip()
    return line[:comment_position].strip()


class TaskRc(dict):
    """ Access the user's taskRC using a dictionary-like interface.

    There is a downside, though:

    Unfortunately, collapsing our configuration into a dict has a
    jarring limitation -- we can't store both of the following
    simultaneously:

    * color = on
    * color.header = something

    In this module, we err on the side of storing subkeys rather than the
    actual value in situations where both are necessary.

    Please forgive me.

    """

    rcdir = None
    UDA_TYPE_MAP = {
        'date': DateField,
        'duration': DurationField,
        'numeric': NumericField,
        'string': StringField,
    }

    def __init__(self, path=None, overrides=None):
        self.overrides = overrides if overrides else {}
        binary_path = shutil.which("task")
        share_rc_path = None
        if binary_path is not None:
            binary_path = os.path.realpath(binary_path) # Normalizes any potential symlinks.
            prefix = os.path.dirname(os.path.dirname(binary_path)) # $prefix/bin/task → $prefix
            share_rc_path = os.path.join(prefix, "share", "doc", "task", "rc") # $prefix/share/doc/task/rc contains additional files.

        self.fallback_prefixes = list(filter(None, [
            share_rc_path
        ]))

        if path:
            self.path = os.path.normpath(
                os.path.expanduser(
                    path
                )
            )
            if not self.rcdir:
                TaskRc.rcdir = os.path.dirname(os.path.realpath(self.path))
                self.fallback_prefixes.append(TaskRc.rcdir)
            config = self._read(self.path)
        else:
            self.path = None
            config = {}

        super(TaskRc, self).__init__(config)

    def _add_to_tree(self, config, key, value):
        key_parts = key.split('.')
        cursor = config
        for part in key_parts[0:-1]:
            if part not in cursor:
                cursor[part] = {}
            # See class docstring -- we can't store both a value and
            # a dict in the same place.
            if not isinstance(cursor[part], dict):
                cursor[part] = {}
            cursor = cursor[part]
        cursor[key_parts[-1]] = value
        return config

    def _merge_trees(self, left, right):
        if left is None:
            left = {}

        for key, value in right.items():
            # See class docstring -- we can't store both a value and
            # a dict in the same place.
            if not isinstance(left, dict):
                left = {}
            if isinstance(value, dict):
                left[key] = self._merge_trees(left.get(key), value)
            else:
                left[key] = value

        return left

    def _read(self, path):
        config = {}

        if not os.path.exists(path):
            # include path may be given relative to dir of rcfile
            oldpath = path
            tries = []
            for fallback_prefix in self.fallback_prefixes:
                path = os.path.join(fallback_prefix, oldpath)
                if not os.path.exists(path):
                    tries.append(path)
                    logger.warn(
                        "tried %s and %s with no success",
                        oldpath, path
                    )
                else:
                    break
            if len(tries) == self.fallback_prefixes:
                logger.error(
                    "failed to find a fallback prefix for %s",
                    oldpath
                )
                raise FileNotFoundError

        with open(path, 'r') as config_file:
            for raw_line in config_file.readlines():
                line = sanitize(raw_line)
                if not line:
                    continue
                if line.startswith('include '):
                    try:
                        left, right = line.split(' ')
                        config = self._merge_trees(
                            config,
                            TaskRc(right.strip())
                        )
                    except ValueError:
                        logger.exception(
                            "Error encountered while adding TaskRc at "
                            "'%s' (from TaskRc file at '%s')",
                            right.strip(),
                            self.path
                        )
                else:
                    try:
                        left, right = line.split('=', 1)
                        key = left.strip()
                        value = right.strip()
                        config = self._add_to_tree(config, key, value)
                    except ValueError:
                        logger.exception(
                            "Error encountered while processing configuration "
                            "setting '%s' (from TaskRc file at '%s')",
                            line,
                            self.path,
                        )

        return self._merge_trees(config, self.overrides)

    def __delitem__(self, *args):
        raise TypeError('TaskRc objects are immutable')

    def __setitem__(self, item, value):
        raise TypeError('TaskRc objects are immutable')

    def update(self, value):
        raise TypeError('TaskRc objects are immutable')

    def get_udas(self):
        raw_udas = self.get('uda', {})
        udas = {}

        for k, v in raw_udas.items():
            tw_type = v.get('type', '')
            label = v.get('label', None)
            choices = v.get('values', None)

            kwargs = {}
            cls = self.UDA_TYPE_MAP.get(tw_type, StringField)
            if choices:
                cls = ChoiceField
                kwargs['choices'] = choices.split(',')
            if label:
                kwargs['label'] = label

            udas[k] = cls(**kwargs)

        return udas

    def __str__(self):
        return 'TaskRc file at {path}'.format(
            path=self.path
        )
