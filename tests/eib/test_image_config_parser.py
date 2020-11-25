# Tests for ImageConfigParser

import eib
import io
import os
from textwrap import dedent

from ..util import SRCDIR


def get_combined_ini(config):
    """Get the combined config as a string"""
    with io.StringIO() as buf:
        config.write(buf)
        return buf.getvalue()


def test_missing(tmp_path, config):
    """Test reading missing config file

    ConfigParser succeeds if the path doesn't exist, which happens a lot
    because config files for all attributes of the build
    (product/arch/etc) are read.
    """
    assert config.read(tmp_path / 'missing') == []
    assert config.sections() == []
    assert get_combined_ini(config) == ''


def test_interpolation(tmp_path, config):
    """Test value interpolation"""
    f = tmp_path / 'f.ini'
    f.write_text(dedent("""\
    [build]
    a = a
    b = b

    [a]
    a = b
    c = c

    d = ${a}
    e = ${a:a}
    f = ${build:a}
    g = ${b}
    h = ${c}
    i = ${d}
    """))
    assert config.read(f) == [str(f)]

    sect = config['a']
    assert sect['d'] == 'b'
    assert sect['e'] == 'b'
    assert sect['f'] == 'a'
    assert sect['g'] == 'b'
    assert sect['h'] == 'c'
    assert sect['i'] == 'b'


def test_config_multiple(tmp_path, config):
    """Test multipile config files combined"""
    f1 = tmp_path / 'f1.ini'
    f1.write_text(dedent("""\
    [a]
    a = a
    b = b
    """))

    f2 = tmp_path / "f2.ini"
    f2.write_text(dedent("""\
    [a]
    b = c
    c = c

    [b]
    a = a
      b
    """))

    assert config.read(f1) == [str(f1)]
    assert config.read(f2) == [str(f2)]

    assert config.sections() == ['a', 'b']
    assert config.options('a') == ['a', 'b', 'c']
    assert config.options('b') == ['a']
    assert config['a']['a'] == 'a'
    assert config['a']['b'] == 'c'
    assert config['a']['c'] == 'c'
    assert config['b']['a'] == 'a\nb'

    expected_combined = dedent("""\
    [a]
    a = a
    b = c
    c = c

    [b]
    a = a
    \tb

    """)
    assert get_combined_ini(config) == expected_combined


def test_merged_option(config):
    """Test option merging"""
    config.MERGED_OPTIONS = [('sect', 'opt')]
    config.add_section('sect')

    # Standard add/del counters
    sect = config['sect']
    sect['opt_add_1'] = 'foo bar baz'
    sect['opt_add_2'] = 'baz'
    sect['opt_del_1'] = 'bar baz'
    config.merge()

    assert set(sect) == {'opt'}

    # The values will be sorted and newline separated
    assert sect['opt'] == 'baz\nfoo'

    # Now that the merged option exists, it will override any further
    # add/del.
    sect['opt_add_1'] = 'bar'
    sect['opt_del_1'] = 'foo'
    config.merge()

    assert set(sect) == {'opt'}
    assert sect['opt'] == 'baz\nfoo'


def test_merged_option_interpolation(config):
    """Test option merging with interpolation"""
    config.MERGED_OPTIONS = [('sect', 'opt')]
    config.add_section('sect')

    sect = config['sect']
    sect['opt_add_1'] = 'foo'
    sect['opt_add_2'] = 'bar baz'
    sect['opt_del_1'] = '${opt_add_1} baz'
    config.merge()

    assert set(sect) == {'opt'}

    assert sect['opt'] == 'bar'


def test_merged_pattern_section(config):
    """Test option merging in a patterned section"""
    config.MERGED_OPTIONS = [('sect-*', 'opt')]
    config.add_section('sect-a')
    a = config['sect-a']
    config.add_section('sect-b')
    b = config['sect-b']

    a['opt_add_test'] = 'foo\n  bar'
    a['opt_del_test'] = 'bar'
    b['opt'] = 'baz'
    b['opt_add_test'] = 'foo'
    config.merge()

    assert 'opt_add_test' not in a
    assert 'opt_del_test' not in a
    assert a['opt'] == 'foo'
    assert 'opt_add_test' not in b
    assert b['opt'] == 'baz'


def test_merged_files(tmp_path, config):
    """Test option merging from files"""
    config.MERGED_OPTIONS = [('sect', 'opt'), ('sect-*', 'opt')]
    a = tmp_path / 'a.ini'
    a.write_text(dedent("""\
    [sect]
    opt_add_a =
      foo
      bar
      baz

    [sect-a]
    opt_add_a =
      foo
      bar

    [sect-b]
    opt = baz
    """))

    b = tmp_path / 'b.ini'
    b.write_text(dedent("""\
    [sect]
    opt_add_b =
      baz

    [sect-a]
    opt_del_b = bar

    [sect-b]
    opt_add_b = foo
    """))

    c = tmp_path / 'c.ini'
    c.write_text(dedent("""\
    [sect]
    opt_del_c =
      bar
      baz
    """))

    assert config.read(a) == [str(a)]
    assert config.read(b) == [str(b)]
    assert config.read(c) == [str(c)]
    config.merge()

    assert set(config['sect']) == {'opt'}
    assert config['sect']['opt'] == 'baz\nfoo'
    assert set(config['sect-a']) == {'opt'}
    assert config['sect-a']['opt'] == 'foo'
    assert set(config['sect-b']) == {'opt'}
    assert config['sect-b']['opt'] == 'baz'


def test_defaults(builder_config):
    """Test defaults.ini can be loaded and resolved"""
    defaults = os.path.join(SRCDIR, 'config/defaults.ini')
    assert builder_config.read(defaults) == [defaults]
    for sect in builder_config:
        # Make sure all the values can be resolved
        builder_config.items(sect)


def test_all_current():
    """Test all current files can be loaded successfully"""
    src_configdir = os.path.join(SRCDIR, 'config')
    for cur, dirs, files in os.walk(src_configdir):
        for name in files:
            if not name.endswith('.ini'):
                continue
            if name == 'local.ini':
                continue
            path = os.path.join(cur, name)
            config = eib.ImageConfigParser()
            assert config.read(path) == [path]
            assert get_combined_ini(config) != ''
