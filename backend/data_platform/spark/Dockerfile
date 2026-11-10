# Spark 4.1.4 (Java 17, Python 3.10) plus what applyInPandas needs. Python 3.10 caps pandas at 2.3.
FROM apache/spark:4.1.4-python3
USER root
RUN pip3 install --no-cache-dir pandas==2.3.3 numpy==2.2.6 pyarrow==21.0.0
USER spark
