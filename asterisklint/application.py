# vim: set ts=8 sw=4 sts=4 et ai:
import os
from importlib import import_module

from .defines import ErrorDef, WarningDef

# 1:
# # SOURCE: main/pbx.c: pbx_substitute_variables_helper_full
# die zoekt naar ${} of $[] en zoekt daarbinnen naar balanced } of resp. ]
# (zonder escaping), daarna wordt replacement gedaan:
# ${} => if endswith () => ast_func_read2, anders ast_str_retrieve_variable
# $[] =>


# 2: run app, bijv, Set, die een split doet, en dan dit:
# # int pbx_builtin_setvar_helper(struct ast_channel *chan,
#     const char *name, const char *value)
# L:                 return ast_func_write(chan, function, value);
# R:
#


if 'we_dont_want_two_linefeeds_between_classdefs':  # for flake8
    class E_APP_WSH(ErrorDef):
        message = 'whitespace before app {app!r} will result in unknown app'

    class E_APP_MISSING(ErrorDef):
        message = 'app {app!r} does not exist, dialplan will halt here!'

    class W_APP_BALANCE(WarningDef):
        message = ('app data {data!r} looks like unbalanced'
                   'parenthesis/quotes/curlies')

    class W_APP_BAD_CASE(WarningDef):
        message = 'app {app!r} does not have the proper Case {proper!r}'

    class W_APP_NEED_PARENS(WarningDef):
        message = 'app {app!r} should have parentheses (only NoOp is exempt)'

    class W_APP_WSH(ErrorDef):
        message = 'unexpected whitespace after app {app!r}'


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


class AppLoader(metaclass=Singleton):
    def __init__(self, version='v11'):
        self.version = version
        self._lower_apps = {}
        self._used_apps = set()

        self.load_all()

    @property
    def used_modules(self):
        return list(filter(
            (lambda x: x != 'unknown'),
            sorted(set(
                [self._lower_apps[i].module
                 for i in self._used_apps]))))

    def load_all(self):
        # Load all from our version dir.
        appsdir = os.path.join(os.path.dirname(__file__),
                               'app', self.version)
        appsmods = [i[0:-3] for i in os.listdir(appsdir) if i.endswith('.py')]

        for appsmod in appsmods:
            mod_name = 'asterisklint.app.{}.{}'.format(self.version, appsmod)
            mod = import_module(mod_name)
            if hasattr(mod, 'register'):
                mod.register(self)

    def get(self, lower_app):
        # Fetch app named lower_app. If it doesn't exist, we alias the
        # 'Unknown' app to it.
        if lower_app not in self._lower_apps:
            # TODO: at this point we want an error raised here, right?
            self._lower_apps[lower_app] = self._lower_apps['unknown']

        self._used_apps.add(lower_app)
        return self._lower_apps[lower_app]

    def register(self, app):
        lower_app = app.name.lower()
        self._lower_apps[lower_app] = app


class App(object):
    # App heeft weer z'n eigen parsers en subparsers. Hiermee moeten we ook
    # op kunnen zoeken welke modules er nodig zijn (w00t). Deze komt ook als
    # eerste in aanmerking voor 1.4 vs. 1.8 differences (ExecIf..., vs
    # ExecIf...?)
    # Ook dumpen van alle variabelen (in dat geval moet de subparser aangeven
    # dat een Var geset wordt (Set() en MSet() doen dat bijv.) en ARRAY() en
    # HASH().
    # Parser en subparsers implementeren volgens included modules?
    # Klinkt wat overkill? Maar maakt het wel mooi extensible. De ExecIf()
    # kan dan de args weer splitten en teruggeven...
    #
    # Per subparser kunnen we de versienummers opgeven:
    # SPRINTF() voor < 1.2 => None
    # SPRINTF() voor >= 1.2 < 1.4 => behaviour X
    # SPRINTF() voor >= 1.4 => behaviour Y
    #
    # Hoe pakken we dan app_compat settings voor Set? Hm.
    def __init__(self, app, where):
        # FIXME: parse app
        self.raw = app
        self.where = where

        # Attempt to parse the app + data.
        self.parse()

    def parse(self):
        """
        Parse self.raw into an App and data. Recursively replaces the
        app data as far as possible.

        It tries to find a specific handler for the application, but
        will fall back to a default handler (parse_simple) if it cannot
        be found.
        """
        # Fetch the Application. If we don't know specifically, we can
        # call the parse_simple on it.
        if not self.split_app_data():
            return

        # Find the handler from the registered handlers. If there is no
        # custom handler, we may already raise a message here.
        app = AppLoader().get(self.app_lower)

        # Pass the data through a handler -- which also handles
        # functions -- first:
        # SOURCE: main/pbx.c: pbx_substitute_variables_helper_full
        # TODO: here..
        self.data = self.data  # this stuff..

        # Check app availability.
        if app.name != self.app:
            if app.name == 'Unknown':
                E_APP_MISSING(self.where, app=self.app)
            else:
                W_APP_BAD_CASE(self.where, app=self.app, proper=app.name)

        # Run data through app.
        app(self.data, where=self.where)

    def split_app_data(self):
        """
        Splits self.raw into self.app, self.app_lower, self.data.
        """
        try:
            app, data = self.raw.split('(', 1)
        except ValueError:
            # We allow NoOp without parentheses. The others need parens.
            app = self.raw
            if self.raw.lower() != 'noop':
                W_APP_NEED_PARENS(self.where, app=app)
            data = '()'
        else:
            data = '(' + data

        # SOURCE: pbx/pbx_config.c: pbx_load_config()
        if data.startswith('(') and data.endswith(')'):
            data = data[1:-1]
        else:
            W_APP_NEED_PARENS(self.where)

        # Set it and try to find a handler for it.
        self.app = app
        self.app_lower = app.lower()
        self.data = data

        # Leading whitespace is frowned upon but allowed. Trailing
        # whitespace won't work:
        if self.app.rstrip() != self.app:
            E_APP_WSH(self.where, app=self.app)
            return False
        if self.app.lstrip() != self.app:
            W_APP_WSH(self.where, app=self.app)
            self.app = self.app.lstrip()
            self.app_lower = self.app.lower()
        # Quick check that the app doesn't exist.
        if not self.app:
            E_APP_MISSING(self.where, app='(none)')
            return False

        return True

    @property
    def name(self):
        return self.app