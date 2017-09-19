# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant::configure("2") do |config|
  config.vm.box = "ubuntu/trusty64"
  config.vm.synced_folder "salt", "/srv/salt/"

  provision_salt = Proc.new do |salt|
    salt.masterless = true
    salt.run_highstate = true
    salt.colorize = true
    salt.verbose = true
    salt.log_level = "error"
  end

  config.vm.define "bosun" do |bosun|
    bosun.vm.hostname = "bosun"
    bosun.vm.provision :salt, &provision_salt
  end

  config.vm.define "postgres" do |postgres|
    postgres.vm.hostname = "postgres"
    postgres.vm.provision :salt, &provision_salt

    if File.directory?(File.expand_path("../heap"))
      postgres.vm.synced_folder "../heap/docker/citus/session_analytics", "/home/vagrant/session_analytics"
    end
  end

  config.vm.define "duo" do |duo|
    duo.vm.hostname = "duo"
    duo.vm.provision :salt, &provision_salt
  end

  config.vm.define "duo-vpn-001" do |duo|
    duo.vm.hostname = "duo-vpn-001"
    duo.vm.provision :salt, &provision_salt
  end

  config.vm.define "fluentd" do |fluentd|
    fluentd.vm.hostname = "fluentd"
    fluentd.vm.provision :salt, &provision_salt
  end


  config.vm.define "tester" do |tester|
  end
end
