{% include 'build.Dockerfile' %}
RUN ulimit -n 10000 && apt-get install \
    python
