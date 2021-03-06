#!/usr/bin/python
# -*- coding: utf-8 -*-
"""HDXObject abstract class containing helper functions for creating, checking, and updating HDX objects.
New HDX objects should extend this in similar fashion to Resource for example.
"""
import abc
import copy
import logging
from collections import UserDict
from typing import Optional, List, Tuple, TypeVar, Union

from ckanapi.errors import NotFound

from hdx.configuration import Configuration
from hdx.utilities.dictandlist import merge_two_dictionaries
from hdx.utilities.loader import load_yaml_into_existing_dict, load_json_into_existing_dict

logger = logging.getLogger(__name__)

HDXObjectUpperBound = TypeVar('T', bound='HDXObject')


class HDXError(Exception):
    pass


class HDXObject(UserDict):
    """HDXObject abstract class containing helper functions for creating, checking, and updating HDX objects.
    New HDX objects should extend this in similar fashion to Resource for example.

    Args:
        initial_data (dict): Initial metadata dictionary
    """
    __metaclass__ = abc.ABCMeta

    @staticmethod
    @abc.abstractmethod
    def actions() -> dict:
        """Dictionary of actions that can be performed on object

        Returns:
            dict: Dictionary of actions that can be performed on object
        """
        pass

    def __init__(self, initial_data: dict):
        super(HDXObject, self).__init__(initial_data)
        self.old_data = None

    def get_old_data_dict(self) -> None:
        """Get previous internal dictionary

        Returns:
            dict: Previous internal dictionary
        """
        return self.old_data

    def update_from_yaml(self, path: str) -> None:
        """Update metadata with static metadata from YAML file

        Args:
            path (str): Path to YAML dataset metadata

        Returns:
            None
        """
        self.data = load_yaml_into_existing_dict(self.data, path)

    def update_from_json(self, path: str):
        """Update metadata with static metadata from JSON file

        Args:
            path (str): Path to JSON dataset metadata

        Returns:
            None
        """
        self.data = load_json_into_existing_dict(self.data, path)

    def _read_from_hdx(self, object_type: str, value: str, fieldname: str = 'id',
                       action: Optional[str] = None,
                       **kwargs) -> Tuple[bool, Union[dict, str]]:
        """Makes a read call to HDX passing in given parameter.

        Args:
            object_type (str): Description of HDX object type (for messages)
            value (str): Value of HDX field
            fieldname (str): HDX field name. Defaults to id.
            action (Optional[str]): Replacement CKAN action url to use. Defaults to None.
            **kwargs: Other fields to pass to CKAN.

        Returns:
            Tuple[bool, Union[dict, str]]: (True/False, HDX object metadata/Error)
        """
        if not fieldname:
            raise HDXError("Empty %s field name!" % object_type)
        if action is None:
            action = self.actions()['show']
        data = {fieldname: value}
        data.update(kwargs)
        try:
            result = Configuration.remoteckan().call_action(action, data,
                                                            requests_kwargs={
                                                                'auth': Configuration.read()._get_credentials()})
            return True, result
        except NotFound:
            return False, "%s=%s: not found!" % (fieldname, value)
        except Exception as e:
            raise HDXError('Failed when trying to read: %s=%s! (POST)' % (fieldname, value)) from e

    def _load_from_hdx(self, object_type: str, id_field: str) -> bool:
        """Helper method to load the HDX object given by identifier from HDX

        Args:
            object_type (str): Description of HDX object type (for messages)
            id_field (str): HDX object identifier

        Returns:
            bool: True if loaded, False if not
        """
        success, result = self._read_from_hdx(object_type, id_field)
        if success:
            self.old_data = self.data
            self.data = result
            return True
        logger.debug(result)
        return False

    @staticmethod
    @abc.abstractmethod
    def read_from_hdx(id_field: str) -> Optional[HDXObjectUpperBound]:
        """Abstract method to read the HDX object given by identifier from HDX and return it

        Args:
            id_field (str): HDX object identifier

        Returns:
            Optional[T <= HDXObject]: HDX object if successful read, None if not
        """
        return

    def _check_existing_object(self, object_type: str, id_field_name: str) -> None:
        if not self.data:
            raise HDXError("No data in %s!" % object_type)
        if id_field_name not in self.data:
            raise HDXError("No %s field (mandatory) in %s!" % (id_field_name, object_type))

    def _check_load_existing_object(self, object_type: str, id_field_name: str) -> None:
        """Check metadata exists and contains HDX object identifier, and if so load HDX object

        Args:
            object_type (str): Description of HDX object type (for messages)
            id_field_name (str): Name of field containing HDX object identifier

        Returns:
            None
        """
        self._check_existing_object(object_type, id_field_name)
        if not self._load_from_hdx(object_type, self.data[id_field_name]):
            raise HDXError("No existing %s to update!" % object_type)

    @abc.abstractmethod
    def check_required_fields(self, ignore_dataset_id=False) -> None:
        """Abstract method to check that metadata for HDX object is complete. The parameter ignore_dataset_id should
        be set to True if you intend to add the object to a Dataset object (where it will be created during dataset
        creation).

        Args:
            ignore_dataset_id (bool): Whether to ignore the dataset id. Default is False.

        Returns:
            None
        """
        return

    def _check_required_fields(self, object_type: str, ignore_fields: List[str]) -> None:
        """Helper method to check that metadata for HDX object is complete

        Args:
            ignore_fields (List[str]): Any fields to ignore in the check

        Returns:
            None
        """
        for field in Configuration.read()['%s' % object_type]['required_fields']:
            if field not in self.data and field not in ignore_fields:
                raise HDXError("Field %s is missing in %s!" % (field, object_type))

    def _merge_hdx_update(self, object_type: str, id_field_name: str, file_to_upload: Optional[str] = None) -> None:
        """Helper method to check if HDX object exists and update it

        Args:
            object_type (str): Description of HDX object type (for messages)
            id_field_name (str): Name of field containing HDX object identifier
            file_to_upload (Optional[str]): File to upload to HDX

        Returns:
            None
        """
        merge_two_dictionaries(self.data, self.old_data)
        ignore_dataset_id = Configuration.read()['%s' % object_type].get('ignore_dataset_id_on_update', False)
        self.check_required_fields(ignore_dataset_id=ignore_dataset_id)
        self._save_to_hdx('update', id_field_name, file_to_upload)

    @abc.abstractmethod
    def update_in_hdx(self) -> None:
        """Abstract method to check if HDX object exists in HDX and if so, update it

        Returns:
            None
        """
        return

    def _update_in_hdx(self, object_type: str, id_field_name: str, file_to_upload: Optional[str] = None) -> None:
        """Helper method to check if HDX object exists in HDX and if so, update it

        Args:
            object_type (str): Description of HDX object type (for messages)
            id_field_name (str): Name of field containing HDX object identifier
            file_to_upload (Optional[str]): File to upload to HDX

        Returns:
            None
        """

        self._check_load_existing_object(object_type, id_field_name)
        self._merge_hdx_update(object_type, id_field_name, file_to_upload)

    def _write_to_hdx(self, action: str, data: dict, id_field_name: str, file_to_upload: Optional[str] = None) -> dict:
        """Creates or updates an HDX object in HDX and return HDX object metadata dict

        Args:
            action (str): Action to perform eg. 'create', 'update'
            data (dict): Data to write to HDX
            id_field_name (str): Name of field containing HDX object identifier or None
            file_to_upload (Optional[str]): File to upload to HDX

        Returns:
            dict: HDX object metadata
        """
        file = None
        try:
            if file_to_upload:
                file = open(file_to_upload, 'rb')
                files = [('upload', file)]
            else:
                files = None
            return Configuration.remoteckan().call_action(self.actions()[action], data, files=files,
                                                          requests_kwargs={
                                                              'auth': Configuration.read()._get_credentials()})
        except Exception as e:
            raise HDXError('Failed when trying to %s %s! (POST)' % (action, self.data[id_field_name])) from e
        finally:
            if file_to_upload and file:
                file.close()

    def _save_to_hdx(self, action: str, id_field_name: str, file_to_upload: Optional[str] = None) -> None:
        """Creates or updates an HDX object in HDX, saving current data and replacing with returned HDX object data
        from HDX

        Args:
            action (str): Action to perform: 'create' or 'update'
            id_field_name (str): Name of field containing HDX object identifier
            file_to_upload (Optional[str]): File to upload to HDX

        Returns:
            None
        """
        result = self._write_to_hdx(action, self.data, id_field_name, file_to_upload)
        self.old_data = self.data
        self.data = result

    @abc.abstractmethod
    def create_in_hdx(self) -> None:
        """Abstract method to check if resource exists in HDX and if so, update it, otherwise create it

        Returns:
            None
        """
        return

    def _create_in_hdx(self, object_type: str, id_field_name: str, name_field_name: str,
                       file_to_upload: Optional[str] = None) -> None:
        """Helper method to check if resource exists in HDX and if so, update it, otherwise create it


        Args:
            object_type (str): Description of HDX object type (for messages)
            id_field_name (str): Name of field containing HDX object identifier
            name_field_name (str): Name of field containing HDX object name
            file_to_upload (Optional[str]): File to upload to HDX (if url not supplied)

        Returns:
            None
        """
        self.check_required_fields()
        if id_field_name in self.data and self._load_from_hdx(object_type, self.data[id_field_name]):
            logger.warning('%s exists. Updating %s' % (object_type, self.data[id_field_name]))
            self._merge_hdx_update(object_type, id_field_name, file_to_upload)
        else:
            self._save_to_hdx('create', name_field_name, file_to_upload)

    @abc.abstractmethod
    def delete_from_hdx(self) -> None:
        """Abstract method to deletes a resource from HDX

        Returns:
            None
        """
        return

    def _delete_from_hdx(self, object_type: str, id_field_name: str) -> None:
        """Helper method to deletes a resource from HDX

        Args:
            object_type (str): Description of HDX object type (for messages)
            id_field_name (str): Name of field containing HDX object identifier

        Returns:
            None
        """
        if id_field_name not in self.data:
            raise HDXError("No %s field (mandatory) in %s!" % (id_field_name, object_type))
        self._save_to_hdx('delete', id_field_name)

    def _addupdate_hdxobject(self, hdxobjects: List[HDXObjectUpperBound], id_field: str,
                             new_hdxobject: HDXObjectUpperBound) -> HDXObjectUpperBound:
        """Helper function to add a new HDX object to a supplied list of HDX objects or update existing metadata if the object
        already exists in the list

        Args:
            hdxobjects (list[T <= HDXObject]): List of HDX objects to which to add new objects or update existing ones
            id_field (str): Field on which to match to determine if object already exists in list
            new_hdxobject (T <= HDXObject): The HDX object to be added/updated

        Returns:
            T <= HDXObject: The HDX object which was added or updated
        """
        for hdxobject in hdxobjects:
            if hdxobject[id_field] == new_hdxobject[id_field]:
                merge_two_dictionaries(hdxobject, new_hdxobject)
                return hdxobject
        hdxobjects.append(new_hdxobject)
        return new_hdxobject

    def _convert_hdxobjects(self, hdxobjects: List[HDXObjectUpperBound]) -> List[HDXObjectUpperBound]:
        """Helper function to convert supplied list of HDX objects to a list of dict

        Args:
            hdxobjects (list[T <= HDXObject]): List of HDX objects to convert

        Returns:
            list[dict]: List of HDX objects converted to simple dictionaries
        """
        newhdxobjects = list()
        for hdxobject in hdxobjects:
            newhdxobjects.append(hdxobject.data)
        return newhdxobjects

    def _copy_hdxobjects(self, hdxobjects: List[HDXObjectUpperBound], hdxobjectclass: type,
                         attribute_to_copy: Optional[str] = None) -> List[HDXObjectUpperBound]:
        """Helper function to make a deep copy of a supplied list of HDX objects

        Args:
            hdxobjects (list[T <= HDXObject]): List of HDX objects to copy
            hdxobjectclass (type): Type of the HDX Objects to be copied
            attribute_to_copy (Optional[str]): An attribute to copy over from the HDX object. Defaults to None.

        Returns:
            list[T <= HDXObject]: Deep copy of list of HDX objects
        """
        newhdxobjects = list()
        for hdxobject in hdxobjects:
            newhdxobjectdata = copy.deepcopy(hdxobject.data)
            newhdxobject = hdxobjectclass(newhdxobjectdata)
            if attribute_to_copy:
                value = getattr(hdxobject, attribute_to_copy)
                setattr(newhdxobject, attribute_to_copy, value)
            newhdxobjects.append(newhdxobject)
        return newhdxobjects

    def _separate_hdxobjects(self, hdxobjects: List[HDXObjectUpperBound], hdxobjects_name: str, id_field: str,
                             hdxobjectclass: type) -> None:
        """Helper function to take a list of HDX objects contained in the internal dictionary and add them to a
        supplied list of HDX objects or update existing metadata if any objects already exist in the list. The list in
        the internal dictionary is then deleted.

        Args:
            hdxobjects (list[T <= HDXObject]): List of HDX objects to which to add new objects or update existing ones
            hdxobjects_name (str): Name of key in internal dictionary from which to obtain list of HDX objects
            id_field (str): Field on which to match to determine if object already exists in list
            hdxobjectclass (type): Type of the HDX Object to be added/updated

        Returns:
            None
        """
        new_hdxobjects = self.data.get(hdxobjects_name, list())
        """:type : List[HDXObjectUpperBound]"""
        if new_hdxobjects:
            hdxobject_names = set()
            for hdxobject in hdxobjects:
                hdxobject_name = hdxobject[id_field]
                hdxobject_names.add(hdxobject_name)
                for new_hdxobject in new_hdxobjects:
                    if hdxobject_name == new_hdxobject[id_field]:
                        merge_two_dictionaries(hdxobject, new_hdxobject)
                        break
            for new_hdxobject in new_hdxobjects:
                if not new_hdxobject[id_field] in hdxobject_names:
                    hdxobjects.append(hdxobjectclass(new_hdxobject))
            del self.data[hdxobjects_name]
