{% set VERSION = '2.1.0' %}

download_tar:
  archive.extracted:
    - name: /home/vagrant/duo_openvpn
    - source: https://github.com/duosecurity/duo_openvpn/tarball/dce643fc4f91a27583fb7e60ab52f5dcad3411d2
    - source_hash: md5=64dd8a4bbdeb1f21ba98b47e77ffff92
    - user: vagrant
    - archive_format: tar

make_duo_openvpn:
  cmd.run:
    - name: make
    - cwd: /home/vagrant/duo_openvpn/duosecurity-duo_openvpn-dce643f
    - creates: /home/vagrant/duo_openvpn/duosecurity-duo_openvpn-dce643f/duo_openvpn.so
    - require:
      - archive: download_tar

construct_duo_install_dir:
  file.directory:
    - name: /tmp/duo
    - user: vagrant

install_duo:
  cmd.run:
    - name: make install DESTDIR=/tmp/duo
    - cwd: /home/vagrant/duo_openvpn/duosecurity-duo_openvpn-dce643f
    - creates: /tmp/duo/opt

patch_python_script:
  file.managed:
    - name: /tmp/duo/opt/duo/duo_openvpn.py
    - source: salt://files/duo/duo_openvpn_vpn_001.py

package_duo:
  cmd.run:
    - name: fpm -s dir -t deb -n "duo-openvpn-vpn-001" -v {{ VERSION }} -C /tmp/duo opt
    - creates: /vagrant/duo-openvpn-vpn-001{{ VERSION }}_amd64.deb
    - cwd: /vagrant
    - user: vagrant
    - require:
      - gem: fpm
