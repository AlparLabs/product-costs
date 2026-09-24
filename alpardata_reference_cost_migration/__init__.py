from . import migration


def post_init_hook(env):
    migration.run(env)
