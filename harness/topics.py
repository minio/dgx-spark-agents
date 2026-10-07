"""The 40 Apache Iceberg topics the fleet sessions study, and the questions each session asks."""

TOPICS = [
    ("partitioning", "api/src/main/java/org/apache/iceberg/PartitionSpec.java"),
    ("partition evolution", "core/src/main/java/org/apache/iceberg/BaseUpdatePartitionSpec.java"),
    ("schema evolution", "core/src/main/java/org/apache/iceberg/SchemaUpdate.java"),
    ("snapshot expiration", "core/src/main/java/org/apache/iceberg/RemoveSnapshots.java"),
    ("manifest merging", "core/src/main/java/org/apache/iceberg/ManifestMergeManager.java"),
    ("table metadata files", "core/src/main/java/org/apache/iceberg/TableMetadataParser.java"),
    ("transactions", "core/src/main/java/org/apache/iceberg/BaseTransaction.java"),
    ("delete file indexing", "core/src/main/java/org/apache/iceberg/DeleteFileIndex.java"),
    ("deletion vectors", "core/src/main/java/org/apache/iceberg/deletes/BaseDVFileWriter.java"),
    ("sort orders", "api/src/main/java/org/apache/iceberg/SortOrder.java"),
    ("branches and tags", "api/src/main/java/org/apache/iceberg/SnapshotRef.java"),
    ("time travel", "core/src/main/java/org/apache/iceberg/util/SnapshotUtil.java"),
    ("metadata tables", "core/src/main/java/org/apache/iceberg/MetadataTableUtils.java"),
    ("scan planning", "core/src/main/java/org/apache/iceberg/DataTableScan.java"),
    ("column metrics", "core/src/main/java/org/apache/iceberg/MetricsUtil.java"),
    ("Puffin statistics files", "core/src/main/java/org/apache/iceberg/puffin/PuffinWriter.java"),
    ("views", "core/src/main/java/org/apache/iceberg/view/ViewMetadata.java"),
    ("the REST catalog", "core/src/main/java/org/apache/iceberg/rest/RESTSessionCatalog.java"),
    ("name mapping", "core/src/main/java/org/apache/iceberg/mapping/NameMapping.java"),
    ("partition transforms", "api/src/main/java/org/apache/iceberg/transforms/Transforms.java"),
    ("the bucket transform", "api/src/main/java/org/apache/iceberg/transforms/Bucket.java"),
    ("table properties", "core/src/main/java/org/apache/iceberg/TableProperties.java"),
    ("snapshot summaries", "core/src/main/java/org/apache/iceberg/SnapshotSummary.java"),
    ("overwrite operations", "core/src/main/java/org/apache/iceberg/BaseOverwriteFiles.java"),
    ("row deltas", "core/src/main/java/org/apache/iceberg/BaseRowDelta.java"),
    ("fast appends", "core/src/main/java/org/apache/iceberg/FastAppend.java"),
    ("rewriting manifests", "core/src/main/java/org/apache/iceberg/BaseRewriteManifests.java"),
    ("cherry-picking snapshots", "core/src/main/java/org/apache/iceberg/CherryPickOperation.java"),
    ("file IO", "core/src/main/java/org/apache/iceberg/io/ResolvingFileIO.java"),
    ("table encryption", "core/src/main/java/org/apache/iceberg/encryption/StandardEncryptionManager.java"),
    ("catalog commits", "core/src/main/java/org/apache/iceberg/BaseMetastoreTableOperations.java"),
    ("the JDBC catalog", "core/src/main/java/org/apache/iceberg/jdbc/JdbcCatalog.java"),
    ("incremental append scans", "core/src/main/java/org/apache/iceberg/BaseIncrementalAppendScan.java"),
    ("changelog scans", "core/src/main/java/org/apache/iceberg/BaseIncrementalChangelogScan.java"),
    ("position deletes", "core/src/main/java/org/apache/iceberg/deletes/PositionDeleteIndex.java"),
    ("equality deletes", "core/src/main/java/org/apache/iceberg/deletes/EqualityDeleteWriter.java"),
    ("manifest files", "core/src/main/java/org/apache/iceberg/ManifestWriter.java"),
    ("metadata columns and row lineage", "core/src/main/java/org/apache/iceberg/MetadataColumns.java"),
    ("default values", "core/src/main/java/org/apache/iceberg/SingleValueParser.java"),
    ("the variant type", "core/src/main/java/org/apache/iceberg/variants/Variants.java"),
]


def questions(topic, path):
    return [
        f"I want to understand {topic} in Apache Iceberg. Read format/spec.md from start to end: "
        f"it is long, so read it in consecutive chunks until you reach the last line. Then explain "
        f"what the specification says about {topic} and why it is designed that way.",
        f"Now read {path} in full and the code it calls for {topic}. Explain how the implementation "
        f"follows the specification, citing file and line.",
        f"What can go wrong with {topic}? List the edge cases and failure modes, and how the code "
        f"guards against each, citing file and line.",
        f"How do query engines use {topic}? Find where this repository's Spark or Flink integration "
        f"relies on it and explain, citing file and line.",
        f"Summarize {topic} for a new contributor in ten bullet points, each with a file and line "
        f"to read first.",
    ]
