import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


def bootstrap_data_dir(data_dir: Path, bootstrap_dir: Path) -> None:
    """Copia dados iniciais para o volume quando o banco ainda não existe."""
    db_path = data_dir / "festejo.db"
    if db_path.exists():
        return

    if not (bootstrap_dir / "festejo.db").exists():
        logger.warning("Bootstrap: festejo.db não encontrado em %s", bootstrap_dir)
        return

    logger.info("Bootstrap: copiando dados iniciais de %s para %s", bootstrap_dir, data_dir)

    data_dir.mkdir(parents=True, exist_ok=True)

    for subdir in ("uploads", "nfe"):
        src = bootstrap_dir / subdir
        if src.exists():
            shutil.copytree(src, data_dir / subdir, dirs_exist_ok=True)

    shutil.copy2(bootstrap_dir / "festejo.db", db_path)
    logger.info("Bootstrap: dados iniciais copiados com sucesso")
