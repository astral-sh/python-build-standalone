{% include 'base.debian13.Dockerfile' %}

RUN apt-get install \
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
