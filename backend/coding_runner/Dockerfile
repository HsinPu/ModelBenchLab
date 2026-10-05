FROM python@sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3
RUN pip install --no-cache-dir numpy==2.2.6
COPY runner.py /runner/runner.py
LABEL modelbench.coding.version="1"
ENV OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
USER 65534:65534
WORKDIR /tmp
ENTRYPOINT ["python", "-I", "/runner/runner.py"]
