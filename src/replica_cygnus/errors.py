class ReplicaError(Exception):
    """Error base del sistema de réplica."""


class ConfigurationError(ReplicaError):
    """Configuración inválida o incompleta."""


class SchemaError(ReplicaError):
    """Error de estructura, columnas o tipos."""


class SyncError(ReplicaError):
    """Error durante una sincronización."""
