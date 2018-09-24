{% set VERSION = '0.0.2' %}

install_nodejs:
  pkg.installed:
    - sources:
      - nodejs: salt://files/nodejs_6.14.4-1nodesource1_amd64.deb

install_kafka_native_packages:
  pkg.installed:
    - pkgs:
      - build-essential
      - openssl
      - libssl-dev
      - libsasl2-dev
    - require:
      - pkg: install_nodejs

kafka_native_repo:
  git.latest:
    - name: https://github.com/heap/node-kafka-native.git
    - target: /home/vagrant/heap/usr/local/heap/node_modules/kafka-native
    - user: vagrant
    - force_fetch: True
    - rev: 'master'

kafka_native_npm_deps:
  cmd.run:
    - name: npm install
    - cwd: /home/vagrant/heap/usr/local/heap/node_modules/kafka-native

install_node_gyp:
  cmd.run:
    - name: npm install -g node-gyp

kafka_native_node_gyp_configure:
  cmd.run:
    - name: node-gyp configure --gcc_version=48
    - user: root
    - cwd: /home/vagrant/heap/usr/local/heap/node_modules/kafka-native

kafka_native_node_gyp_build:
  cmd.run:
    - name: node-gyp build
    - user: root
    - cwd: /home/vagrant/heap/usr/local/heap/node_modules/kafka-native
    - require:
        - cmd: kafka_native_node_gyp_configure

remove_git_data:
  cmd.run:
    - name: rm -r /home/vagrant/heap/usr/local/heap/node_modules/kafka-native/.git
    - user: root

package_kafka_native:
  cmd.run:
    - name: fpm -s dir -t deb -n "kafka-native" -v {{ VERSION }} -C /home/vagrant/heap usr
    - creates: /vagrant/kafka-_{{ VERSION }}_amd64.deb
    - cwd: /vagrant
    - user: vagrant
    - require:
      - gem: fpm
