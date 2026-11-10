"""PySpark rewrite of Axiom's indicator code, checked against it and timed against pandas.

    python -m data_platform.spark.bench          # downloads H.10, builds the image, runs both, compares

Spark runs in Docker (image pinned in Dockerfile). Nothing here is used by the app or the agents.
"""
