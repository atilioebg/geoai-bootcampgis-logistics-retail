FROM postgis/postgis:16-3.4

# Install build dependencies (excluding git as requested)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    postgresql-server-dev-16 \
    clang-13 \
    llvm-13 \
    flex \
    bison \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install pgvector (v0.6.2)
RUN wget https://github.com/pgvector/pgvector/archive/refs/tags/v0.6.2.tar.gz -O pgvector.tar.gz && \
    tar -xzf pgvector.tar.gz && \
    cd pgvector-0.6.2 && \
    make && make install && \
    cd .. && rm -rf pgvector.tar.gz pgvector-0.6.2

# Install apache/age (PG16 branch)
RUN wget https://github.com/apache/age/archive/refs/heads/PG16.tar.gz -O age.tar.gz && \
    tar -xzf age.tar.gz && \
    cd age-PG16 && \
    make && make install && \
    cd .. && rm -rf age.tar.gz age-PG16
