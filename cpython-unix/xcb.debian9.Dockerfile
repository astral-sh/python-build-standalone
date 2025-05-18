{% include 'build.debian9.Dockerfile' %}
RUN ulimit -n 10000 && apt-get install \
    python
