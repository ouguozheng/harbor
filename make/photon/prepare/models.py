import os
import logging
from pathlib import Path
from shutil import copytree, rmtree

from g import internal_tls_dir, DEFAULT_GID, DEFAULT_UID, PG_GID, PG_UID
from utils.misc import check_permission, owner_can_read, other_can_read, get_realpath, owner_can_read


class Config:
    def __init__(self, config_dict: dict):
        self.internal_tls = InternalTLS(config_dict.get('internal_tls'), config_dict['data_volume'])


class InternalTLS:

    harbor_certs_filename = {
        'harbor_internal_ca.crt',
        'core.crt', 'core.key',
        'job_service.crt', 'job_service.key',
        'registry_ctl.crt', 'registry_ctl.key'
    }

    clair_certs_filename = {
        'clair_adapter.crt', 'clair_adapter.key',
        'clair.crt', 'clair.key'
    }

    notary_certs_filename = {
        'notary_signer.crt', 'notary_signer.key',
        'notary_server.crt', 'notary_server.key'
    }

    chart_museum_filename = {
        'chart_museum.crt',
        'chart_museum.key'
    }

    db_certs_filename = {
        'harbor_db.crt', 'harbor_db.key'
    }

    def __init__(self, tls_dir: str, data_volume:str, **kwargs):
        if not tls_dir:
            self.enabled = False
        self.enabled = True
        self.tls_dir = tls_dir
        self.data_volume = data_volume
        self.required_filenames = self.harbor_certs_filename
        if kwargs.get('with_clair'):
            self.required_filenames.update(self.clair_certs_filename)
        if kwargs.get('with_notary'):
            self.required_filenames.update(self.notary_certs_filename)
        if kwargs.get('with_chartmuseum'):
            self.required_filenames.update(self.chart_museum_filename)

    def __getattribute__(self, name: str):
        """
        internal_tls.core_crt_path
        """
        # only handle when enabled tls and name ends with 'path'
        if name.endswith('_path'):
            if not (self.enabled):
                return object.__getattribute__(self, name)

            name_parts = name.split('_')
            if len(name_parts) < 3:
                return object.__getattribute__(self, name)

            filename = '{}.{}'.format('_'.join(name_parts[:-2]), name_parts[-2])

            if filename in self.required_filenames:
                return os.path.join(self.data_volume, filename)

        return object.__getattribute__(self, name)

    def _check(self, filename: str):
        """
        Check the permission of cert and key is correct
        """

        path = os.path.join(internal_tls_dir, filename)

        if not path.exists:
            if filename == 'harbor_internal_ca.crt':
                return
            raise Exception('File {} not exist'.format(filename))

        if not path.is_file:
            raise Exception('invalid {}'.format(filename))

        # check key file permission
        if filename.endswith('.key') and not check_permission(path, mode=0o600):
            raise Exception('key file {} permission is not 600'.format(filename))

        # check owner can read cert file
        if filename.endswith('.crt') and not owner_can_read(path.stat().st_mode):
                raise Exception('File {} should readable by owner'.format(filename))

    def validate(self) -> bool:
        if not self.enabled:
            return True

        if not internal_tls_dir.exists():
            raise Exception('Internal dir for tls {} not exist'.format(internal_tls_dir))

        for filename in self.required_filenames:
            self._check(filename)

        return True

    def prepare(self):
        if not self.enabled:
            logging.info('internal tls NOT enabled...')
            return
        original_tls_dir = get_realpath(self.tls_dir)
        rmtree(internal_tls_dir)
        copytree(original_tls_dir, internal_tls_dir, symlinks=True)

        for file in internal_tls_dir.iterdir():
            if file.name.endswith('.key'):
                file.chmod(0o600)
            elif file.name.endswith('.crt'):
                file.chmod(0o644)

            if file.name in self.db_certs_filename:
                os.chown(file, PG_UID, PG_GID)
            else:
                os.chown(file, DEFAULT_UID, DEFAULT_GID)


