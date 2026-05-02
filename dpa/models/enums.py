from enum import Enum


class DataTier(str, Enum):
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"


class ColumnType(str, Enum):
    STRING = "string"
    INTEGER = "integer"
    LONG = "long"
    DOUBLE = "double"
    FLOAT = "float"
    BOOLEAN = "boolean"
    TIMESTAMP = "timestamp"
    DATE = "date"
    DECIMAL = "decimal"
    BINARY = "binary"
    ARRAY = "array"
    MAP = "map"
    STRUCT = "struct"


class QualityRuleType(str, Enum):
    NOT_NULL = "not_null"
    UNIQUE = "unique"
    EMAIL_FORMAT = "email_format"
    REGEX = "regex"
    ACCEPTED_VALUES = "accepted_values"
    MIN_VALUE = "min_value"
    MAX_VALUE = "max_value"
    ROW_COUNT_BETWEEN = "row_count_between"
    FRESHNESS_HOURS = "freshness_hours"


class PartitionTransform(str, Enum):
    IDENTITY = "identity"
    YEAR = "year"
    MONTH = "month"
    DAY = "day"
    HOUR = "hour"
    BUCKET = "bucket"
    TRUNCATE = "truncate"
