{% include 'base.debian9.Dockerfile' %}

RUN ulimit -n 10000 && apt-get install \
    bzip2 \
    file \
    libc6-dev \
    libffi-dev \
    make \
    patch \
    perl \
    pkg-config \
    tar \
    xz-utils \
    unzip \
    zip \
    zlib1g-dev
