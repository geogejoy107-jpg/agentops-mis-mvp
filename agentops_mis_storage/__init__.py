"""Storage adapter helpers for AgentOps MIS.

The default Free Local runtime remains SQLite and standard-library only.
Optional modules in this package are imported by BYOC/commercial smokes and
future adapters only when their optional dependencies are available.
"""

__all__ = ["parity_fixture", "postgres"]
