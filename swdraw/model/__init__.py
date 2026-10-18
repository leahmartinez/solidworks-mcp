"""3D parts: inspect a part and edit it from a spec, with a self-check after the rebuild."""
from .edit import backup_path, edit  # noqa: F401
from .part import inspect, open_part  # noqa: F401
from .spec import load_spec, validate_edit_spec  # noqa: F401
