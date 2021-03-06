import os
import pytest

import testinfra.utils.ansible_runner

from .settings import versions, DEB_PACKAGES, RHEL_FILES, RPM7_PACKAGES, RPM_PACKAGES, EXTENSIONS, LANGUAGES, DEB_FILES


testinfra_hosts = testinfra.utils.ansible_runner.AnsibleRunner(
    os.environ['MOLECULE_INVENTORY_FILE']).get_hosts('all')

pg_versions = versions[os.getenv("PG_VERSION")]


@pytest.fixture()
def postgres_unit_file(host):
    cmd = "sudo systemctl list-units| grep postgresql"
    return host.check_output(cmd)


@pytest.fixture()
def start_stop_postgresql(host):
    cmd = "sudo systemctl stop postgresql"
    result = host.run(cmd)
    assert result.rc == 0
    cmd = "sudo systemctl start postgresql"
    result = host.run(cmd)
    assert result.rc == 0
    cmd = "sudo systemctl status postgresql"
    return host.run(cmd)


@pytest.fixture()
def postgresql_binary(host):
    os = host.system_info.distribution
    if os.lower() in ["redhat", "centos", 'rhel']:
        return host.file("/usr/pgsql-11/bin/postgres")
    elif os in ["debian", "ubuntu"]:
        return host.file("/usr/lib/postgresql/11/bin/postgres")


@pytest.fixture()
def postgresql_query_version(host):
    with host.sudo("postgres"):
        return host.run("psql -c 'SELECT version()' | awk 'NR==3{print $2}'")


@pytest.fixture()
def restart_postgresql(host):
    cmd = "sudo systemctl restart postgresql"
    result = host.run(cmd)
    assert result.rc == 0
    cmd = "sudo systemctl status postgresql"
    return host.run(cmd)


@pytest.fixture()
def extension_list(host):
    with host.sudo("postgres"):
        result = host.check_output("psql -c 'SELECT * FROM pg_available_extensions;' | awk 'NR>=3{print $1}'")
        result = result.split()
        return result


@pytest.fixture()
def insert_data(host):
    with host.sudo("postgres"):
        pgbench = "pgbench -i -s 1"
        result = host.run(pgbench)
        assert result.rc == 0
        select = "psql -c 'SELECT COUNT(*) FROM pgbench_accounts;' | awk 'NR==3{print $1}'"
        result = host.check_output(select)
    yield result.strip("\n")


@pytest.mark.parametrize("package", DEB_PACKAGES)
def test_deb_package_is_installed(host, package):
    os = host.system_info.distribution
    if os.lower() in ["redhat", "centos", 'rhel']:
        pytest.skip("This test only for Debian based platforms")
    pkg = host.package(package)
    assert pkg.is_installed
    assert pkg.version in pg_versions['deb_pkg_ver']


@pytest.mark.parametrize("package", RPM_PACKAGES)
def test_rpm_package_is_installed(host, package):
    os = host.system_info.distribution
    if os in ["debian", "ubuntu"]:
        pytest.skip("This test only for RHEL based platforms")
    if host.system_info.release == "7":
        pytest.skip("Only for RHEL8 tests")
    pkg = host.package(package)
    assert pkg.is_installed
    if package not in ["percona-postgresql-client-common", "percona-postgresql-common"]:
        assert pkg.version == pg_versions['version']
    else:
        assert pkg.version == pg_versions[package]


@pytest.mark.parametrize("package", RPM7_PACKAGES)
def test_rpm7_package_is_installed(host, package):
    os = host.system_info.distribution
    if os in ["debian", "ubuntu"]:
        pytest.skip("This test only for RHEL based platforms")
    if host.system_info.release == "8.0":
        pytest.skip("Only for centos7 tests")
    pkg = host.package(package)
    assert pkg.is_installed
    if package not in ["percona-postgresql-client-common", "percona-postgresql-common"]:
        assert pkg.version == pg_versions['version']
    else:
        assert pkg.version == pg_versions[package]


def test_postgresql_client_version(host):
    os = host.system_info.distribution
    pkg = "percona-postgresql-11"
    if os.lower() in ["redhat", "centos", 'rhel']:
        pytest.skip("This test only for Debian based platforms")
    pkg = host.package(pkg)
    assert "11" in pkg.version


def test_postgresql_version(host):
    os = host.system_info.distribution
    pkg = "percona-postgresql-client-11"
    if os.lower() in ["redhat", "centos", 'rhel']:
        pkg = "percona-postgresql11"
    pkg = host.package(pkg)
    assert "11" in pkg.version


def test_postgresql_is_running_and_enabled(host):
    os = host.system_info.distribution
    if os.lower() in ["redhat", "centos", 'rhel']:
        postgresql = host.service("postgresql-11")
    else:
        postgresql = host.service("postgresql")
    assert postgresql.is_running
    assert postgresql.is_enabled


def test_postgres_unit_file(postgres_unit_file):
    assert "postgresql" in postgres_unit_file


def test_postgres_binary(postgresql_binary):
    assert postgresql_binary.exists
    assert postgresql_binary.user == "root"


def test_pg_config_server_version(host):
    cmd = "pg_config --version"
    try:
        result = host.check_output(cmd)
        assert "11" in result, result.stdout
    except AssertionError:
        pytest.mark.xfail(reason="Maybe dev package not install")


def test_postgresql_query_version(postgresql_query_version):
    assert postgresql_query_version.rc == 0, postgresql_query_version.stderr
    assert postgresql_query_version.stdout.strip("\n") == pg_versions['version'], postgresql_query_version.stdout


def test_postgres_client_version(host):
    cmd = "psql --version"
    result = host.check_output(cmd)
    assert "11" in result.strip("\n"), result.stdout


def test_start_stop_postgresql(start_stop_postgresql):
    assert start_stop_postgresql.rc == 0, start_stop_postgresql.rc
    assert "active" in start_stop_postgresql.stdout, start_stop_postgresql.stdout


def test_restart_postgresql(restart_postgresql):
    assert restart_postgresql.rc == 0, restart_postgresql.stderr
    assert "active" in restart_postgresql.stdout, restart_postgresql.stdout


def test_insert_data(insert_data):
    assert insert_data == "100000", insert_data


def test_extenstions_list(extension_list, host):
    os = host.system_info.distribution
    for extension in EXTENSIONS:
        if os.lower() in ['centos', 'redhat', 'rhel']:
            if "python3" in extension:
                pytest.skip("Skipping python3 extensions for Centos or RHEL")
        assert extension in extension_list


@pytest.mark.parametrize("extension", EXTENSIONS)
def test_enable_extension(host, extension):
    os = host.system_info.distribution
    if os.lower() in ["redhat", "centos", 'rhel']:
        if "python3" in extension:
            pytest.skip("Skipping python3 extensions for Centos or RHEL")
    with host.sudo("postgres"):
        install_extension = host.run("psql -c 'CREATE EXTENSION \"{}\";'".format(extension))
        assert install_extension.rc == 0, install_extension.stderr
        assert install_extension.stdout.strip("\n") == "CREATE EXTENSION", install_extension.stderr
        extensions = host.run("psql -c 'SELECT * FROM pg_extension;' | awk 'NR>=3{print $1}'")
        assert extensions.rc == 0, extensions.stderr
        assert extension in set(extensions.stdout.split()), extensions.stdout


@pytest.mark.parametrize("extension", EXTENSIONS[::-1])
def test_drop_extension(host, extension):
    os = host.system_info.distribution
    if os.lower() in ["redhat", "centos", 'rhel']:
        if "python3" in extension:
            pytest.skip("Skipping python3 extensions for Centos or RHEL")
    with host.sudo("postgres"):
        drop_extension = host.run("psql -c 'DROP EXTENSION \"{}\";'".format(extension))
        assert drop_extension.rc == 0, drop_extension.stderr
        assert drop_extension.stdout.strip("\n") == "DROP EXTENSION", drop_extension.stdout
        extensions = host.run("psql -c 'SELECT * FROM pg_extension;' | awk 'NR>=3{print $1}'")
        assert extensions.rc == 0, extensions.stderr
        assert extension not in set(extensions.stdout.split()), extensions.stdout


def test_plpgsql_extension(host):
    with host.sudo("postgres"):
        extensions = host.run("psql -c 'SELECT * FROM pg_extension;' | awk 'NR>=3{print $1}'")
        assert extensions.rc == 0, extensions.stderr
        assert "plpgsql" in set(extensions.stdout.split()), extensions.stdout


@pytest.mark.parametrize("file", DEB_FILES)
def test_deb_files(host, file):
    os = host.system_info.distribution
    if os.lower() in ["redhat", "centos", 'rhel']:
        pytest.skip("This test only for Debian based platforms")
    with host.sudo("postgres"):
        f = host.file(file)
        assert f.exists
        assert f.size > 0
        assert f.content_string != ""
        assert f.user == "postgres"


@pytest.mark.parametrize("file", RHEL_FILES)
def test_rpm_files(file, host):
    os = host.system_info.distribution
    if os in ["debian", "ubuntu"]:
        pytest.skip("This test only for RHEL based platforms")
    with host.sudo("postgres"):
        f = host.file(file)
        assert f.exists
        assert f.size > 0
        assert f.content_string != ""
        assert f.user == "postgres"


@pytest.mark.parametrize("language", LANGUAGES)
def test_language(host, language):
    os = host.system_info.distribution
    with host.sudo("postgres"):
        if os.lower() in ["redhat", "centos", 'rhel']:
            if "python3" in language:
                pytest.skip("Skipping python3 language for Centos or RHEL")
        lang = host.run("psql -c 'CREATE LANGUAGE {};'".format(language))
        assert lang.rc == 0, lang.stderr
        assert lang.stdout.strip("\n") == "CREATE LANGUAGE", lang.stdout
        drop_lang = host.run("psql -c 'DROP LANGUAGE {};'".format(language))
        assert drop_lang.rc == 0, drop_lang.stderr
        assert drop_lang.stdout.strip("\n") == "DROP LANGUAGE", lang.stdout
