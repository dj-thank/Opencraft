"""Private local workspace: OS-account trust, no network or provider credentials."""
from __future__ import annotations

from pathlib import Path
import os
import stat

from .auth import Principal, TokenAuthority
from .database import Database
from .service import CanonicalWorldService, ServiceError


class LocalWorkspace:
    def __init__(self, directory: str | Path, *, create: bool = False) -> None:
        requested = Path(directory).expanduser().absolute()
        if requested.is_symlink():
            raise ServiceError("unsafe-directory", "workspace directory must not be a symlink")
        if not requested.exists():
            if not create:
                raise ServiceError("not-initialized", "run opencraft-mcp --init first", status=409)
            requested.mkdir(parents=True, mode=0o700)
        self.directory = requested.resolve()
        information = self.directory.stat()
        if not stat.S_ISDIR(information.st_mode):
            raise ServiceError("unsafe-directory", "workspace must be a directory")
        if os.name != "nt":
            if information.st_uid != os.getuid() or information.st_mode & 0o077:
                raise ServiceError("unsafe-directory", "workspace must be owned by this user with mode 0700")
        for name in ("world.sqlite3", "token-pepper.bin"):
            if (self.directory / name).is_symlink():
                raise ServiceError("unsafe-directory", "workspace data files must not be symlinks")
        if not create and not (self.directory / "world.sqlite3").is_file():
            raise ServiceError("not-initialized", "run opencraft-mcp --init first", status=409)
        self.database = Database(self.directory / "world.sqlite3")
        self.authority = TokenAuthority.from_data_directory(self.directory)
        self.service = CanonicalWorldService(self.database, self.authority)
        self.actor: Principal = self.service.local_principal(create=create)
        if os.name != "nt":
            self.database.path.chmod(0o600)

    def context(self, **kwargs):
        return self.service.context(self.actor, **kwargs)
