"""Compatibility module."""
from __future__ import unicode_literals
import ctypes
import sys
import os
import stat
import re
import unicodedata
from functools import wraps
import warnings

PY34 = (3, 4) <= sys.version_info
PY35 = (3, 5) <= sys.version_info
PY36 = (3, 6) <= sys.version_info
PY37 = (3, 7) <= sys.version_info
PY310 = (3, 10) <= sys.version_info
PY312 = (3, 12) <= sys.version_info

UNICODE = 0
BYTES = 1

CASE_FS = os.path.normcase('A') != os.path.normcase('a')

RE_NORM = re.compile(
    r'''(?x)
    (/|\\/)|
    (\\[abfnrtv\\])|
    (\\(?:U[\da-fA-F]{8}|u[\da-fA-F]{4}|x[\da-fA-F]{2}|([0-7]{1,3})))|
    (\\N\{[^}]*?\})|
    (\\[^NUux]) |
    (\\[NUux])
    '''
)

RE_BNORM = re.compile(
    br'''(?x)
    (/|\\/)|
    (\\[abfnrtv\\])|
    (\\(?:x[\da-fA-F]{2}|([0-7]{1,3})))|
    (\\[^x]) |
    (\\[x])
    '''
)

BACK_SLASH_TRANSLATION = {
    r"\a": '\a',
    r"\b": '\b',
    r"\f": '\f',
    r"\r": '\r',
    r"\t": '\t',
    r"\n": '\n',
    r"\v": '\v',
    r"\\": r'\\',
    br"\a": b'\a',
    br"\b": b'\b',
    br"\f": b'\f',
    br"\r": b'\r',
    br"\t": b'\t',
    br"\n": b'\n',
    br"\v": b'\v',
    br"\\": br'\\'
}

if sys.platform.startswith('win'):
    _PLATFORM = "windows"
elif sys.platform == "darwin":  # pragma: no cover
    _PLATFORM = "osx"
else:
    _PLATFORM = "linux"


def platform():
    """Get platform."""

    return _PLATFORM


def is_case_sensitive():
    """Check if case sensitive."""

    return CASE_FS


def norm_pattern(pattern, normalize, is_raw_chars, ignore_escape=False):
    r"""
    Normalize pattern.

    - For windows systems we want to normalize slashes to \.
    - If raw string chars is enabled, we want to also convert
      encoded string chars to literal characters.
    - If `normalize` is enabled, take care to convert \/ to \\\\.
    """

    if isinstance(pattern, bytes):
        is_bytes = True
        slash = b'\\'
        multi_slash = slash * 4
        pat = RE_BNORM
    else:
        is_bytes = False
        slash = '\\'
        multi_slash = slash * 4
        pat = RE_NORM

    if not normalize and not is_raw_chars and not ignore_escape:
        return pattern

    def norm(m):
        """Normalize the pattern."""

        if m.group(1):
            char = m.group(1)
            if normalize and len(char) > 1:
                char = multi_slash
        elif m.group(2):
            char = BACK_SLASH_TRANSLATION[m.group(2)] if is_raw_chars else m.group(2)
        elif is_raw_chars and m.group(4):
            char = bytes([int(m.group(4), 8) & 0xFF]) if is_bytes else chr(int(m.group(4), 8))
        elif is_raw_chars and m.group(3):
            char = bytes([int(m.group(3)[2:], 16)]) if is_bytes else chr(int(m.group(3)[2:], 16))
        elif is_raw_chars and not is_bytes and m.group(5):
            char = unicodedata.lookup(m.group(5)[3:-1])
        elif not is_raw_chars or m.group(5 if is_bytes else 6):
            char = m.group(0)
            if ignore_escape:
                char = slash + char
        else:
            value = m.group(6) if is_bytes else m.group(7)
            pos = m.start(6) if is_bytes else m.start(7)
            raise SyntaxError("Could not convert character value {!r} at position {:d}".format(value, pos))
        return char

    return pat.sub(norm, pattern)


class StringIter:
    """Preprocess replace tokens."""

    def __init__(self, string):
        """Initialize."""

        self._string = string
        self._index = 0

    def __iter__(self):
        """Iterate."""

        return self

    def __next__(self):
        """Python 3 iterator compatible next."""

        return self.iternext()

    def match(self, pattern):
        """Perform regex match at index."""

        m = pattern.match(self._string, self._index)
        if m:
            self._index = m.end()
        return m

    @property
    def index(self):
        """Get current index."""

        return self._index

    def previous(self):  # pragma: no cover
        """Get previous char."""

        return self._string[self._index - 1]

    def advance(self, count):  # pragma: no cover
        """Advanced the index."""

        self._index += count

    def rewind(self, count):
        """Rewind index."""

        if count > self._index:  # pragma: no cover
            raise ValueError("Can't rewind past beginning!")

        self._index -= count

    def iternext(self):
        """Iterate through characters of the string."""

        try:
            char = self._string[self._index]
            self._index += 1
        except IndexError:  # pragma: no cover
            raise StopIteration

        return char


class Immutable:
    """Immutable."""

    __slots__ = tuple()

    def __init__(self, **kwargs):
        """Initialize."""

        for k, v in kwargs.items():
            super(Immutable, self).__setattr__(k, v)

    def __setattr__(self, name, value):  # pragma: no cover
        """Prevent mutability."""

        raise AttributeError('Class is immutable!')


def is_hidden(path):
    """Check if file is hidden."""

    hidden = False
    f = os.path.basename(path)
    if f[:1] in ('.', b'.'):
        # Count dot file as hidden on all systems
        hidden = True
    elif sys.platform == 'win32':
        # On Windows, look for `FILE_ATTRIBUTE_HIDDEN`
        FILE_ATTRIBUTE_HIDDEN = 0x2
        if PY35:
            results = os.lstat(path)
            hidden = bool(results.st_file_attributes & FILE_ATTRIBUTE_HIDDEN)
        else:
            if isinstance(path, bytes):
                attrs = ctypes.windll.kernel32.GetFileAttributesA(path)
            else:
                attrs = ctypes.windll.kernel32.GetFileAttributesW(path)
            hidden = attrs != -1 and attrs & FILE_ATTRIBUTE_HIDDEN
    elif sys.platform == "darwin":  # pragma: no cover
        # On macOS, look for `UF_HIDDEN`
        results = os.lstat(path)
        hidden = bool(results.st_flags & stat.UF_HIDDEN)
    return hidden


def deprecated(message, stacklevel=2):  # pragma: no cover
    """
    Raise a `DeprecationWarning` when wrapped function/method is called.

    Usage:

        @deprecated("This method will be removed in version X; use Y instead.")
        def some_method()"
            pass
    """

    def _wrapper(func):
        @wraps(func)
        def _deprecated_func(*args, **kwargs):
            warnings.warn(
                "'{}' is deprecated. {}".format(func.__name__, message),
                category=DeprecationWarning,
                stacklevel=stacklevel
            )
            return func(*args, **kwargs)
        return _deprecated_func
    return _wrapper


def warn_deprecated(message, stacklevel=2):  # pragma: no cover
    """Warn deprecated."""

    warnings.warn(
        message,
        category=DeprecationWarning,
        stacklevel=stacklevel
    )


def _fspath(path):
    """Return the path representation of a path-like object.

    If str or bytes is passed in, it is returned unchanged. Otherwise the
    os.PathLike interface is used to get the path representation. If the
    path representation is not str or bytes, TypeError is raised. If the
    provided path is not str, bytes, or os.PathLike, TypeError is raised.
    """
    if isinstance(path, (str, bytes)):
        return path

    # Work from the object's type to match method resolution of other magic
    # methods.
    path_type = type(path)
    try:
        path_repr = path_type.__fspath__(path)
    except AttributeError:
        if hasattr(path_type, '__fspath__'):
            raise
        else:
            raise TypeError("expected str, bytes or os.PathLike object, "
                            "not " + path_type.__name__)
    if isinstance(path_repr, (str, bytes)):
        return path_repr
    else:
        raise TypeError("expected {}.__fspath__() to return str or bytes, "
                        "not {}".format(path_type.__name__,
                                        type(path_repr).__name__))


if not hasattr(os, 'fspath'):
    fspath = _fspath
    fspath.__name__ = "fspath"
else:
    fspath = os.fspath
