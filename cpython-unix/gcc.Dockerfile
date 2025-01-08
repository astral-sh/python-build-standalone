{% include 'base.Dockerfile' %}
RUN ulimit -n 10000 && apt-get install \
      autoconf \
      automake \
      bison \
      build-essential \
      gawk \
      gcc \
      gcc-multilib \
      libtool \
      make \
      tar \
      texinfo \
      xz-utils \
      unzip
