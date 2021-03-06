#!/usr/bin/python
# -*- coding: utf-8 -*-
"""Resource class containing all logic for creating, checking, and updating resources."""
import csv
import logging
from os import unlink
from os.path import join
from typing import Optional, List, Tuple

from hdx.configuration import Configuration
from hdx.utilities.downloader import Download
from hdx.utilities.loader import load_yaml, load_json
from hdx.utilities.path import script_dir_plus_file
from .hdxobject import HDXObject, HDXError

logger = logging.getLogger(__name__)


class Resource(HDXObject):
    """Resource class containing all logic for creating, checking, and updating resources.

    Args:
        initial_data (Optional[dict]): Initial resource metadata dictionary. Defaults to None.
    """

    def __init__(self, initial_data: Optional[dict] = None):
        if not initial_data:
            initial_data = dict()
        super(Resource, self).__init__(initial_data)
        self.file_to_upload = None

    @staticmethod
    def actions() -> dict:
        """Dictionary of actions that can be performed on object

        Returns:
            dict: Dictionary of actions that can be performed on object
        """
        return {
            'show': 'resource_show',
            'update': 'resource_update',
            'create': 'resource_create',
            'delete': 'resource_delete',
            'search': 'resource_search',
            'datastore_delete': 'datastore_delete',
            'datastore_create': 'datastore_create',
            'datastore_insert': 'datastore_insert',
            'datastore_upsert': 'datastore_upsert'
        }

    def update_from_yaml(self, path: str = join('config', 'hdx_resource_static.yml')) -> None:
        """Update resource metadata with static metadata from YAML file

        Args:
            path (Optional[str]): Path to YAML dataset metadata. Defaults to config/hdx_resource_static.yml.

        Returns:
            None
        """
        super(Resource, self).update_from_yaml(path)

    def update_from_json(self, path: str = join('config', 'hdx_resource_static.json')) -> None:
        """Update resource metadata with static metadata from JSON file

        Args:
            path (Optional[str]): Path to JSON dataset metadata. Defaults to config/hdx_resource_static.json.

        Returns:
            None
        """
        super(Resource, self).update_from_json(path)

    @staticmethod
    def read_from_hdx(identifier: str) -> Optional['Resource']:
        """Reads the resource given by identifier from HDX and returns Resource object

        Args:
            identifier (str): Identifier of resource

        Returns:
            Optional[Resource]: Resource object if successful read, None if not
        """

        resource = Resource()
        result = resource._load_from_hdx('resource', identifier)
        if result:
            return resource
        return None

    def get_file_to_upload(self) -> Optional[str]:
        """Get the file uploaded

        Returns:
            Optional[str]: The file that will be or has been uploaded or None if there isn't one
        """
        return self.file_to_upload

    def set_file_to_upload(self, file_to_upload: str) -> None:
        """Set the file uploaded to the local path provided

        Args:
            file_to_upload (str): Local path to file to upload

        Returns:
            None
        """
        self.file_to_upload = file_to_upload

    def check_required_fields(self, ignore_dataset_id=False) -> None:
        """Check that metadata for resource is complete and add resource_type and url_type if not supplied.
        The parameter ignore_dataset_id should
        be set to True if you intend to add the object to a Dataset object (where it will be created during dataset
        creation).

        Args:
            ignore_dataset_id (bool): Whether to ignore the dataset id. Default is False.

        Returns:
            None
        """
        if self.file_to_upload is None:
            if 'url' in self.data:
                if 'resource_type' not in self.data:
                    self.data['resource_type'] = 'api'
                if 'url_type' not in self.data:
                    self.data['url_type'] = 'api'
            else:
                raise HDXError('Either a url or a file to upload must be supplied!')
        else:
            if 'url' not in self.data:
                self.data['url'] = 'ignore'  # must be set even though overwritten
            if 'resource_type' not in self.data:
                self.data['resource_type'] = 'file.upload'
            if 'url_type' not in self.data:
                self.data['url_type'] = 'upload'
            if 'tracking_summary' in self.data:
                del self.data['tracking_summary']
        if ignore_dataset_id:
            ignore_fields = [Configuration.read()['resource']['dataset_id']]
        else:
            ignore_fields = list()

        self._check_required_fields('resource', ignore_fields)

    def update_in_hdx(self) -> None:
        """Check if resource exists in HDX and if so, update it

        Returns:
            None
        """
        self._update_in_hdx('resource', 'id', self.file_to_upload)

    def create_in_hdx(self) -> None:
        """Check if resource exists in HDX and if so, update it, otherwise create it

        Returns:
            None
        """
        self._create_in_hdx('resource', 'id', 'name', self.file_to_upload)

    def delete_from_hdx(self) -> None:
        """Deletes a resource from HDX

        Returns:
            None
        """
        self._delete_from_hdx('resource', 'id')

    @staticmethod
    def search_in_hdx(query: str, **kwargs) -> List['Resource']:
        """Searches for resources in HDX. NOTE: Does not search dataset metadata!

        Args:
            query (str): Query
            **kwargs: See below
            order_by (str): A field on the Resource model that orders the results
            offset (int): Apply an offset to the query
            limit (int): Apply a limit to the query
        Returns:
            List[Resource]: List of resources resulting from query
        """

        resources = []
        resource = Resource()
        success, result = resource._read_from_hdx('resource', query, 'query', Resource.actions()['search'])
        if result:
            count = result.get('count', None)
            if count:
                for resourcedict in result['results']:
                    resource = Resource(resourcedict)
                    resources.append(resource)
        else:
            logger.debug(result)
        return resources

    def download(self, folder: Optional[str] = None) -> Tuple[str, str]:
        """Download resource store to provided folder or temporary folder if no folder supplied

        Args:
            folder (Optional[str]): Folder to download resource to. Defaults to None.

        Returns:
            Tuple[str, str]: (URL downloaded, Path to downloaded file)

        """
        # Download the resource
        url = self.data.get('url', None)
        if not url:
            raise HDXError('No URL to download!')
        logger.debug('Downloading %s' % url)
        with Download() as download:
            path = download.download_file(url, folder)
            return url, path

    def delete_datastore(self) -> None:
        """Delete a resource from the HDX datastore

        Returns:
            None
        """
        success, result = self._read_from_hdx('datastore', self.data['id'], 'resource_id',
                                              self.actions()['datastore_delete'],
                                              force=True)
        if not success:
            logger.debug(result)

    def create_datastore(self, schema: List[dict] = None, primary_key: Optional[str] = None,
                         delete_first: int = 0, path: Optional[str] = None) -> None:
        """For csvs, create a resource in the HDX datastore which enables data preview in HDX. If no schema is provided
        all fields are assumed to be text. If path is not supplied, the file is first downloaded from HDX.

        Args:
            schema (List[dict]): List of fields and types of form {'id': 'FIELD', 'type': 'TYPE'}. Defaults to None.
            primary_key (Optional[str]): Primary key of schema. Defaults to None.
            delete_first (int): Delete datastore before creation. 0 = No, 1 = Yes, 2 = If no primary key. Defaults to 0.
            path (Optional[str]): Local path to file that was uploaded. Defaults to None.

        Returns:
            None
        """
        if delete_first == 0:
            pass
        elif delete_first == 1:
            self.delete_datastore()
        elif delete_first == 2:
            if primary_key is None:
                self.delete_datastore()
        else:
            raise HDXError('delete_first must be 0, 1 or 2! (0 = No, 1 = Yes, 2 = Delete if no primary key)')
        if path is None:
            # Download the resource
            url, path = self.download()
            delete_after_download = True
        else:
            url = self.data.get('url', None)
            if not url:
                raise HDXError('No URL to download!')
            delete_after_download = False

        f = None
        try:
            f = open(path, 'r')
            reader = csv.DictReader(f)
            if schema is None:
                schema = list()
                for fieldname in reader.fieldnames:
                    schema.append({'id': fieldname, 'type': 'text'})
            data = {'resource_id': self.data['id'], 'force': True, 'fields': schema, 'primary_key': primary_key}
            self._write_to_hdx('datastore_create', data, 'id')
            rows = [row for row in reader]
            chunksize = 10240
            offset = 0
            if primary_key is None:
                method = 'insert'
            else:
                method = 'upsert'
            logger.debug('Uploading data from %s to datastore' % url)
            while offset < len(rows):
                rowset = rows[offset:offset + chunksize]
                data = {'resource_id': self.data['id'], 'force': True, 'method': method, 'records': rowset}
                self._write_to_hdx('datastore_upsert', data, 'id')
                offset += chunksize
                logger.debug('Uploading: %s' % offset)
        except Exception as e:
            raise HDXError('Upload to datastore of %s failed!' % url) from e
        finally:
            if f:
                f.close()
            if delete_after_download:
                unlink(path)

    def create_datastore_from_dict_schema(self, data: dict, delete_first: int = 0, path: Optional[str] = None) -> None:
        """For csvs, create a resource in the HDX datastore which enables data preview in HDX from a dictionary
        containing a list of fields and types of form {'id': 'FIELD', 'type': 'TYPE'} and optionally a primary key.
        If path is not supplied, the file is first downloaded from HDX.

        Args:
            data (dict): Dictionary containing list of fields and types of form {'id': 'FIELD', 'type': 'TYPE'}
            delete_first (int): Delete datastore before creation. 0 = No, 1 = Yes, 2 = If no primary key. Defaults to 0.
            path (Optional[str]): Local path to file that was uploaded. Defaults to None.

        Returns:
            None
        """
        schema = data['schema']
        primary_key = data.get('primary_key')
        self.create_datastore(schema, primary_key, delete_first, path=path)

    def create_datastore_from_yaml_schema(self, yaml_path: str, delete_first: int = 0,
                                          path: Optional[str] = None) -> None:
        """For csvs, create a resource in the HDX datastore which enables data preview in HDX from a YAML file
        containing a list of fields and types of form {'id': 'FIELD', 'type': 'TYPE'} and optionally a primary key.
        If path is not supplied, the file is first downloaded from HDX.

        Args:
            yaml_path (str): Path to YAML file containing list of fields and types of form {'id': 'FIELD', 'type': 'TYPE'}
            delete_first (int): Delete datastore before creation. 0 = No, 1 = Yes, 2 = If no primary key. Defaults to 0.
            path (Optional[str]): Local path to file that was uploaded. Defaults to None.

        Returns:
            None
        """
        data = load_yaml(yaml_path)
        self.create_datastore_from_dict_schema(data, delete_first, path=path)

    def create_datastore_from_json_schema(self, json_path: str, delete_first: int = 0,
                                          path: Optional[str] = None) -> None:
        """For csvs, create a resource in the HDX datastore which enables data preview in HDX from a JSON file
        containing a list of fields and types of form {'id': 'FIELD', 'type': 'TYPE'} and optionally a primary key.
        If path is not supplied, the file is first downloaded from HDX.

        Args:
            json_path (str): Path to JSON file containing list of fields and types of form {'id': 'FIELD', 'type': 'TYPE'}
            delete_first (int): Delete datastore before creation. 0 = No, 1 = Yes, 2 = If no primary key. Defaults to 0.
            path (Optional[str]): Local path to file that was uploaded. Defaults to None.

        Returns:
            None
        """
        data = load_json(json_path)
        self.create_datastore_from_dict_schema(data, delete_first, path=path)

    def create_datastore_for_topline(self, delete_first: int = 0, path: Optional[str] = None):
        """For csvs, create a resource in the HDX datastore which enables data preview in HDX using the built in
        YAML definition for a topline. If path is not supplied, the file is first downloaded from HDX.

        Args:
            delete_first (int): Delete datastore before creation. 0 = No, 1 = Yes, 2 = If no primary key. Defaults to 0.
            path (Optional[str]): Local path to file that was uploaded. Defaults to None.

        Returns:
            None
        """
        data = load_yaml(script_dir_plus_file(join('..', 'hdx_datasource_topline.yml'), Resource))
        self.create_datastore_from_dict_schema(data, delete_first, path=path)

    def update_datastore(self, schema: List[dict] = None, primary_key: Optional[str] = None,
                         path: Optional[str] = None) -> None:
        """For csvs, update a resource in the HDX datastore which enables data preview in HDX. If no schema is provided
        all fields are assumed to be text. If path is not supplied, the file is first downloaded from HDX.

        Args:
            schema (List[dict]): List of fields and types of form {'id': 'FIELD', 'type': 'TYPE'}. Defaults to None.
            primary_key (Optional[str]): Primary key of schema. Defaults to None.
            path (Optional[str]): Local path to file that was uploaded. Defaults to None.

        Returns:
            None
        """
        self.create_datastore(schema, primary_key, 2, path=path)

    def update_datastore_from_dict_schema(self, data: dict, path: Optional[str] = None) -> None:
        """For csvs, update a resource in the HDX datastore which enables data preview in HDX from a dictionary
        containing a list of fields and types of form {'id': 'FIELD', 'type': 'TYPE'} and optionally a primary key.
        If path is not supplied, the file is first downloaded from HDX.

        Args:
            data (dict): Dictionary containing list of fields and types of form {'id': 'FIELD', 'type': 'TYPE'}
            path (Optional[str]): Local path to file that was uploaded. Defaults to None.

        Returns:
            None
        """
        self.create_datastore_from_dict_schema(data, 2, path=path)

    def update_datastore_from_yaml_schema(self, yaml_path: str, path: Optional[str] = None) -> None:
        """For csvs, update a resource in the HDX datastore which enables data preview in HDX from a YAML file
        containing a list of fields and types of form {'id': 'FIELD', 'type': 'TYPE'} and optionally a primary key.
        If path is not supplied, the file is first downloaded from HDX.

        Args:
            yaml_path (str): Path to YAML file containing list of fields and types of form {'id': 'FIELD', 'type': 'TYPE'}
            path (Optional[str]): Local path to file that was uploaded. Defaults to None.

        Returns:
            None
        """
        self.create_datastore_from_yaml_schema(yaml_path, 2, path=path)

    def update_datastore_from_json_schema(self, json_path: str, path: Optional[str] = None) -> None:
        """For csvs, update a resource in the HDX datastore which enables data preview in HDX from a JSON file
        containing a list of fields and types of form {'id': 'FIELD', 'type': 'TYPE'} and optionally a primary key.
        If path is not supplied, the file is first downloaded from HDX.

        Args:
            json_path (str): Path to JSON file containing list of fields and types of form {'id': 'FIELD', 'type': 'TYPE'}
            path (Optional[str]): Local path to file that was uploaded. Defaults to None.

        Returns:
            None
        """
        self.create_datastore_from_json_schema(json_path, 2, path=path)

    def update_datastore_for_topline(self, path: Optional[str] = None) -> None:
        """For csvs, update a resource in the HDX datastore which enables data preview in HDX using the built in YAML
        definition for a topline. If path is not supplied, the file is first downloaded from HDX.

        Args:
            path (Optional[str]): Local path to file that was uploaded. Defaults to None.

        Returns:
            None
        """
        self.create_datastore_for_topline(2, path=path)
