{% include 'base.debian9.Dockerfile' %}
RUN ulimit -n 10000 && apt-get install \
      autoconf \
      automake \
      bison \
      build-essential \
      gawk \
      gcc \
      libtool \
      make \
      tar \
      texinfo \
      xz-utils \
      unzip
