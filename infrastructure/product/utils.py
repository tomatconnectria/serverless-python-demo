import os
from pathlib import Path

from git import Repo

import infrastructure.product.constants as constants


def get_username() -> str:
    try:
        return os.getlogin().replace('.', '-')
    except Exception:
        return 'github'


def get_stack_name() -> str:
    repo = Repo(Path.cwd())
    username = get_username()
    try:
        branch_name = f'{repo.active_branch}'.replace('/', '-')
        return f'{username}-{branch_name}-{constants.SERVICE_NAME}'
    except TypeError:
        # we're running in detached mode (HEAD)
        # see https://github.com/gitpython-developers/GitPython/issues/633
        return f'{username}-{constants.SERVICE_NAME}'


def get_construct_name(stack_prefix: str, construct_name: str) -> str:
    return f'{stack_prefix}{construct_name}'[0:64]