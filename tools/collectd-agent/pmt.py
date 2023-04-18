#!/usr/bin/env python

# Copyright (C) 2021-2022 Intel Corporation
# SPDX-License-Identifier: MIT

"""This module provides means of PMT telemetry retrieval.
    When imported, it is used with collectd Python plugin and reports via collect API.
    When run stand-alone, it reports to standard output.
"""

import copy
import json
import platform
import re
import sys
import urllib.request
from urllib.parse import urlparse
from mimetypes import guess_type
from os import path, listdir
from pathlib import Path
import math
from lxml import etree
import argparse

if sys.platform == "win32":
    import wmi
    import win32file
    import winioctlcon
    import struct

    FILE_DEVICE_INTEL_PMT = 0x9998
    INTEL_PMT_TELEMETRY_INTERFACE_GUID = "3dfb2563-5c44-4c59-8d80-baea7d06e6b8"


    def pmt_ioctl(id):
        return winioctlcon.CTL_CODE(FILE_DEVICE_INTEL_PMT, id,
                                    winioctlcon.METHOD_BUFFERED,
                                    winioctlcon.FILE_READ_ACCESS)


    IOCTL_DISCOVERY_SIZE = pmt_ioctl(0x0)
    IOCTL_DISCOVERY = pmt_ioctl(0x1)
    IOCTL_TELEMETRY_DWORD = pmt_ioctl(0x2)
    IOCTL_TELEMETRY_QWORD = pmt_ioctl(0x3)


    def getDriverDeviceIds():
        c = wmi.WMI()
        wql = "SELECT DeviceID FROM Win32_PnPEntity Where name LIKE 'Intel(R) Platform Monitoring Technology (PMT) Driver'"
        return c.query(wql)


    def get_telemetry(interface, use_qwords=False):
        telemetry_ioctl = IOCTL_TELEMETRY_DWORD
        handle = win32file.CreateFile(interface, win32file.GENERIC_READ, 0, None, win32file.OPEN_EXISTING,
                                      win32file.FILE_ATTRIBUTE_NORMAL, None)

        try:
            ret = win32file.DeviceIoControl(handle, IOCTL_DISCOVERY_SIZE, None, 4)

            if ret == None:
                # print("Get discovery failed!")
                exit

            # typedef struct _PMTSW_TELEMETRY_DISCOVERY {
            #     ULONG Version;
            #     ULONG Count;
            #     PMTSW_TELEMETRY_ENTRY Telemetry[ANYSIZE_ARRAY];
            # } PMTSW_TELEMETRY_DISCOVERY, *PPMTSW_TELEMETRY_DISCOVERY;
            size_needed = struct.unpack("L", ret)[0]
            discovery = win32file.DeviceIoControl(handle, IOCTL_DISCOVERY, None, size_needed)

            if discovery == None:
                # print("Get discovery failed!")
                exit

            telemetry = []
            _, count = struct.unpack("LL", discovery[0:8])
            for i in range(count):
                # typedef struct _PMTSW_TELEMETRY_ENTRY {
                #     ULONG Version;          // Structure version
                #     ULONG Index;            // Array index within parent structure
                #     ULONG Guid;             // Globally Unique Id for XML definitions
                #     ULONG DWordCount;       // Count of DWORDs
                # } PMTSW_TELEMETRY_ENTRY, *PPMTSW_TELEMETRY_ENTRY;
                _, idx, guid, dword_count = struct.unpack("LLLL", discovery[8 + i * 16: 24 + i * 16])

                if use_qwords:
                    dword_count /= 2
                    telemetry_ioctl = IOCTL_TELEMETRY_QWORD

                # typedef struct _PMTSW_TELEMETRY_READ {
                #    ULONG Version;     // Structure version
                #    ULONG Index;       // index of telemetry region returned by GetTelemetryDiscovery
                #    ULONG Offset;      // Starting DWORD or QWORD index within telemetry region
                #    ULONG Count;       // Count of DWORD or QWORD to read
                # } PMTSW_TELEMETRY_READ, *PPMTSW_TELEMETRY_READ;
                readrequest = struct.pack("LLLL", 0, idx, 0, int(dword_count))

                ret = win32file.DeviceIoControl(handle, telemetry_ioctl, readrequest, int(dword_count * 8))

                telemetry.append({"guid": guid, "data": ret})

            return telemetry

        finally:
            win32file.CloseHandle(handle)


class PmtXmlParser:
    """Helper class providing static methods for multi-level PMT XML parsing."""

    def __init__(self):
        pass

    @staticmethod
    def localname(name):
        """Function localname returns simplest localname from an etree tag."""
        return etree.QName(name).localname

    @staticmethod
    def remove_ws(data):
        """Function remove_ws strips whitespaces and newlines from its argument."""
        if data is not None:
            return data.replace("\n", "").strip()
        else:
            return data

    @staticmethod
    def get_nested_attr(node):
        """Function get_nested_attr decodes properties of data types such as enumeration."""
        ret = {}
        if node is None:
            return ret
        # iterate over attributes
        for an, av in node.attrib.items():
            ret[PmtXmlParser.localname(an)] = av
        # iterate over child elements
        for n in list(node):
            temp = PmtXmlParser.get_nested_attr(n)
            if temp == {}:
                ret[PmtXmlParser.localname(
                    n.tag)] = PmtXmlParser.remove_ws(n.text)
            else:
                if PmtXmlParser.localname(n.tag) == "enum_item":
                    ret[temp['encoding']] = temp
                else:
                    ret[PmtXmlParser.localname(n.tag)] = temp
        return ret

    @staticmethod
    def parse_data_types(node):
        """Function parse_data_types decodes defined data types."""
        dtypes = {}
        if node is None:
            return dtypes
        for elem in list(node):
            if PmtXmlParser.localname(elem.tag) == 'dataType':
                node_id = elem.get('datatypeID')
                dtypes[node_id] = PmtXmlParser.get_nested_attr(elem)
        return dtypes

    @staticmethod
    def parse_sample_group(node):
        """Function parse_sample_group decodes low level samples definition."""
        t_samples = {}
        t_ret = {"size": 0}
        t_size = 0
        if node is None:
            return t_ret
        for n in list(node):
            if PmtXmlParser.localname(n.tag) == 'sample':
                t = {}
                t['sampleID'] = n.get('sampleID')
                t['datatypeID'] = n.get('datatypeIDREF')
                # sampleID identifies the index of its 64bit container
                t['offset'] = 8 * int(node.get('sampleID'))
                t_size = t['offset']
                for e in list(n):
                    if PmtXmlParser.localname(e.tag) == 'size':
                        t['size'] = e.text
                    elif PmtXmlParser.localname(e.tag) == 'lsb':
                        t['lsb'] = e.text
                    elif PmtXmlParser.localname(e.tag) == 'msb':
                        t['msb'] = e.text
                    elif PmtXmlParser.localname(e.tag) == 'description':
                        t['description'] = PmtXmlParser.remove_ws(e.text)
                    elif PmtXmlParser.localname(e.tag) == 'sampleType':
                        t['sampleType'] = PmtXmlParser.remove_ws(e.text)
                t_samples[n.get('sampleID')] = t
        # size is max offset + 8 (sample size)
        t_ret["size"] = t_size + 8
        t_ret["samples"] = t_samples
        return t_ret

    @staticmethod
    def parse_transformations(node):
        """Function parse_transformations decodes transformation rule and equation."""
        t_trans = {}
        if node is None:
            return
        for n in list(node):
            if PmtXmlParser.localname(n.tag) == 'TransFormation':
                t = {}
                t['transformID'] = n.get('transformID')
                for e in list(n):
                    if PmtXmlParser.localname(e.tag) == 'output_dataclass':
                        t['output_dataclass'] = e.text
                    elif PmtXmlParser.localname(e.tag) == 'transform':
                        t['transform'] = e.text
                    elif PmtXmlParser.localname(e.tag) == 'TransFormParameters':
                        param = []
                        for c in list(e):
                            if PmtXmlParser.localname(c.tag) == 'parameterName':
                                param.append(c.text)
                        t['TransFormParameters'] = param

                t_trans[t['transformID']] = t
        return t_trans

    @staticmethod
    def parse_transform_inputs(node):
        """Function parse_transform_inputs decodes required low level samples
           for transformation inputs."""
        inp = {}
        if node is None:
            return None
        for n in list(node):
            if PmtXmlParser.localname(n.tag) == 'TransFormInput':
                t = {}
                t['varName'] = n.get('varName')
                for e in list(n):
                    if PmtXmlParser.localname(e.tag) == 'sampleIDREF':
                        t['sampleIDREF'] = PmtXmlParser.remove_ws(e.text)
                inp[t['varName']] = t['sampleIDREF']
        return inp

    @staticmethod
    def parse_transform_mapping(node):
        """Function parse_transform_mapping decodes high level sample specification."""
        t_map = {}
        if node is None:
            return
        for n in list(node):
            if PmtXmlParser.localname(n.tag) == 'T_AggregatorSample':
                t = {}
                t['sampleName'] = n.get('sampleGroup') + "." + n.get('sampleName')
                t["datatypeID"] = n.get('datatypeIDREF')
                t['sampleID'] = n.get('sampleID')
                for e in list(n):
                    if PmtXmlParser.localname(e.tag) == "transformREF":
                        t['transformREF'] = PmtXmlParser.remove_ws(e.text)
                    elif PmtXmlParser.localname(e.tag) == "SampleType":
                        t["SampleType"] = PmtXmlParser.remove_ws(e.text)
                    elif PmtXmlParser.localname(e.tag) == 'TransFormInputs':
                        t['inputs'] = PmtXmlParser.parse_transform_inputs(e)

                t_map[t['sampleName']] = t
        return t_map

    @staticmethod
    def get_pmt_dict(bp, guid, xs, allowlist):
        """Function get_pmt_dict loads PMT XML set for UID uid hosted at basepath bp with
        XML set relative path specified by xs. It returns a Python object specifying list of
        low level samples, data types, transformations and transformations mappings.
        This object allows samples retrieval, decoding and transformation programmatically."""

        ret = {}
        ret[guid] = {}

        xmlparser = etree.XMLParser(
            ns_clean=True, remove_comments=True, remove_blank_text=True, resolve_entities=False)

        cm_url = bp + "/" + xs["basedir"] + "/" + xs["common"]
        agg_url = bp + "/" + xs["basedir"] + "/" + xs["aggregator"]
        agi_url = bp + "/" + xs["basedir"] + "/" + xs["aggregatorinterface"]
        # parse common
        cm_tree = etree.parse(cm_url, xmlparser)
        root = cm_tree.getroot()
        datatypes = PmtXmlParser.parse_data_types(root)
        # parse aggregator
        samp_groups = {}
        uniqueid = ""
        telem_size = ""
        agg_tree = etree.parse(agg_url, xmlparser)
        root = agg_tree.getroot()

        for node in list(root):
            lname = ""
            try:
                lname = PmtXmlParser.localname(node.tag)
            except:
                continue

            if lname == 'uniqueid':
                uniqueid = hex(int(node.text, base=16))
            elif lname == 'SampleGroup':
                t_groups = PmtXmlParser.parse_sample_group(node)
                allow_from_list = lambda entry: any(re.match(pattern, entry[0]) for pattern in allowlist)
                filtered_samples = dict(filter(allow_from_list, t_groups["samples"].items()))
                telem_size = t_groups["size"]
                samp_groups.update(filtered_samples)

        # parse aggregator interface
        agi_tree = etree.parse(agi_url, xmlparser)
        root = agi_tree.getroot()
        trans = {}
        tmap = {}
        rev_date = ""
        for node in list(root):
            lname = ""
            try:
                lname = PmtXmlParser.localname(node.tag)
            except:
                continue
            if lname == 'TransFormations':
                trans = PmtXmlParser.parse_transformations(node)
            elif lname == 'AggregatorSamples':
                tmap = PmtXmlParser.parse_transform_mapping(node)
            elif lname == 'revisionDate':
                rev_date = PmtXmlParser.remove_ws(node.text)

        # validate if the unique id and size matches mp
        detected_guid = uniqueid + "_" + str(telem_size)
        if guid != detected_guid:
            print(
                f"GUID mismatched: expecting {guid} found {detected_guid}", file=sys.stderr)
            return ret

        ret[guid]["lastupdated"] = rev_date
        ret[guid]['samples'] = samp_groups
        ret[guid]['datatypes'] = datatypes
        ret[guid]['transformations'] = trans
        ret[guid]['transformations_mapping'] = tmap
        return ret

    @staticmethod
    def parse_xmlset(xs):
        """Function parse_xmlset decodes list of XML files associated with each function."""
        x = {}
        if xs is None:
            return x
        for n in list(xs):
            x[n.tag] = n.text
        return x

    @staticmethod
    def parse_mappings(mp):
        """Function parse_mappings decodes list of the PMT UID and XMLs set definitions."""
        r = {}
        if mp is None:
            return r
        for n in list(mp):
            if n.tag == "mapping":
                guid = n.get("guid")
                size = n.get("size")
                id_num = guid + "_" + size
                r[id_num] = {}
                for c in list(n):
                    if c.tag == "lastupdated":
                        r[id_num]["lastupdated"] = c.text
                    elif c.tag == "status":
                        r[id_num]["status"] = c.text
                    elif c.tag == "description":
                        r[id_num]["description"] = c.text
                    elif c.tag == "xmlset":
                        r[id_num]["xmlset"] = PmtXmlParser.parse_xmlset(c)
        return r

    @staticmethod
    def convert_pmt_to_dict(txml):
        """Function convert_pmt_to_dict parses etree representation into Python object."""
        d = {}
        if txml is None:
            return d
        for n in list(txml):
            if n.tag == 'lastupdated':
                d["lastupdated"] = n.text
            elif n.tag == "mappings":
                d["mappings"] = PmtXmlParser.parse_mappings(n)
        return d

    @staticmethod
    def get_metadata(url):
        """Function get_metadata fetches PMT XML repository metadata from specified url.
        It returns all available PMT UID to XML mappings in this repository."""
        ret = {}
        if url is None:
            return ret
        parser = etree.XMLParser(
            ns_clean=True, remove_comments=True, remove_blank_text=True)
        opener = urllib.request.build_opener()
        try:
            tree = etree.parse(opener.open(url), parser)
            ret = PmtXmlParser.convert_pmt_to_dict(tree.getroot())
        except:
            pass
            # log(f"Exception: {sys.exc_info()[0]}")

        return ret


class PmtPlugin:
    """Class keeping plugin context and callbacks."""

    COLLECTD = 1
    AGENT = 2

    LOG_INFO = 1
    LOG_ERROR = 2

    def __init__(self, mode=AGENT, conf_url='', interval=5, allowlist=[]):
        self.conf = {}
        self.pmt_files = {}
        self.pmt = {}
        self.mode = mode
        if self.mode == self.AGENT:
            self.conf['PMT_URL'] = conf_url
            self.conf["ALLOWLIST"] = allowlist
            self.interval = interval

    def logger(self, log, level=LOG_INFO):
        """Logging wrapper function. Uses collectd built-in or logging module."""
        if self.mode == self.COLLECTD:
            if level == self.LOG_ERROR:
                collectd.error(log)
            else:
                collectd.info(log)
        else:
            # logging module is imported here, because collectd runtime
            # limits the use of threading beforehand.
            if level == self.LOG_ERROR:
                level = logging.ERROR
            else:
                level = logging.INFO
            logging.log(msg=log, level=level)

    def config(self, conf):
        """Collectd configuration callback."""
        if self.mode != self.COLLECTD:
            return
        self.conf = {}
        for kv in conf.children:
            if len(kv.values) == 1:
                self.conf[kv.key] = kv.values[0]
            else:
                self.conf[kv.key] = kv.values

        if 'PMT_URL' not in self.conf:
            self.logger("Option PMT_URL not specified in collectd plugin config. "
                        "No data will be reported.")

        if 'ALLOWLIST_URL' not in self.conf:
            self.conf["ALLOWLIST"] = ['.*']
            self.logger("Option ALLOWLIST not specified in collectd plugin config. "
                        "All metrics are allowed")
        else:
            self.conf["ALLOWLIST"] = file_lines_to_list(self.conf["ALLOWLIST_URL"])

    @staticmethod
    def assert_is_not_symlink(path):
        if Path(path).is_symlink():
            raise IOError(
                f'Unable to open file at path {path}. Per security policy usage of symbolic links shall be avoided.')

    def init(self):
        """Collectd init callback."""
        self.pmt_files = {}
        url_type = guess_type(self.conf['PMT_URL'])
        pmtmeta = {}

        if url_type[0] == 'application/xml' or url_type[0] == 'text/xml':
            xmlbaseurl = path.dirname(self.conf['PMT_URL'])
            pmtmeta = PmtXmlParser.get_metadata(self.conf['PMT_URL'])
        elif url_type[0] == 'application/json':
            with urllib.request.urlopen(self.conf['PMT_URL']) as url:
                pmtmeta = json.loads(url.read().decode())
        else:
            self.logger("Cannot detect PMT_URL file type %s, use JSON or XML." % url_type[0],
                        level=self.LOG_ERROR)
            return False

        # discover pmt sysfs structure
        pmt_root = "/sys/class/intel_pmt"
        pmt_dir = []
        if sys.platform == "linux":
            try:
                pmt_dir = listdir(pmt_root)
            except FileNotFoundError:
                self.logger("Cannot find PMT data (%s)." % pmt_root, level=self.LOG_ERROR)
                return False

            for folder in pmt_dir:
                if folder.startswith("telem"):
                    t_id = ""
                    t_path = ""
                    try:
                        # check if we can read guid and size
                        pmt_root_guid_path = path.join(pmt_root, folder, 'guid')
                        self.assert_is_not_symlink(pmt_root_guid_path)
                        pmt_root_size_path = path.join(pmt_root, folder, 'size')
                        self.assert_is_not_symlink(pmt_root_size_path)

                        with open(pmt_root_guid_path, encoding='utf-8') as f_guid:
                            t_id = f_guid.read().replace("\n", "_")
                        with open(pmt_root_size_path, encoding='utf-8') as f_size:
                            t_id += f_size.read().replace("\n", "")
                        t_path = path.join(pmt_root, folder, 'telem')
                    except IOError:
                        self.logger("PMT endpoint folder %s is invalid" % folder)
                    if t_id == "" and t_path == "":
                        continue
                    if path.isfile(t_path) is False:
                        continue
                    if t_id in self.pmt_files:
                        self.pmt_files[t_id].append(t_path)
                    else:
                        self.pmt_files[t_id] = []
                        self.pmt_files[t_id].append(t_path)
                    # print(self.pmt_files)
                    self.logger("Plugin PMT found PMT endpoint %s at %s" % (t_id, t_path))
        if sys.platform == "win32":
            device_ids = getDriverDeviceIds()
            for device_id in device_ids:
                interface = "//?/" + device_id.DeviceID.replace("\\",
                                                                "#") + "#{" + INTEL_PMT_TELEMETRY_INTERFACE_GUID + "}/"
                telemetry = get_telemetry(interface, use_qwords=True)
                for t in telemetry:
                    t_id = hex(t["guid"]) + "_" + str(len(t["data"]))
                    if t_id in self.pmt_files:
                        self.pmt_files[t_id].append(interface)
                    else:
                        self.pmt_files[t_id] = []
                        self.pmt_files[t_id].append(interface)
        # find discovered guid from pmt meta, load the dictionary, if not found, remove it
        self.pmt = {}
        tmp_pmt_files = copy.deepcopy(self.pmt_files)
        for uid in tmp_pmt_files:
            fragment = uid.split("_")
            candidates = []
            for v in pmtmeta["mappings"].keys():
                if v.startswith(fragment[0]):
                    candidates.append(v)
            # Matching guid only
            if len(candidates) == 1:
                d = PmtXmlParser.get_pmt_dict(xmlbaseurl, candidates[0],
                                              pmtmeta["mappings"][candidates[0]]["xmlset"],
                                              allowlist=self.conf["ALLOWLIST"])
                self.logger("Plugin PMT will decode PMT endpoint %s with specification of %s"
                            % (uid, candidates[0]))
                self.pmt[uid] = d[candidates[0]]
            elif len(candidates) > 1:
                if uid in pmtmeta["mappings"].keys():  # exact match
                    d = PmtXmlParser.get_pmt_dict(xmlbaseurl, uid, pmtmeta["mappings"][uid]["xmlset"],
                                                  allowlist=self.conf["ALLOWLIST"])
                    self.logger("Plugin PMT will decode PMT endpoint %s" % uid)
                    self.pmt[uid] = d[uid]
                else:  # not matching any length, pick up the first instance
                    d = PmtXmlParser.get_pmt_dict(xmlbaseurl, candidates[0],
                                                  pmtmeta["mappings"][candidates[0]]["xmlset"],
                                                  allowlist=self.conf["ALLOWLIST"])
                    self.logger("Plugin PMT will try to decode PMT endpoint %s"
                                " with specification %s", (uid, candidates[0]))
                    self.pmt[uid] = d[candidates[0]]
            else:
                self.pmt_files.pop(uid)
                self.logger("Plugin PMT does not understand PMT endpoint %s" % uid,
                            level=self.LOG_ERROR)
        return True

    @staticmethod
    def safe_eval(eqts):
        """The safe_eval utility is to clean up accepted math equation statement,
        any left over is considered harmful and should not be executed as security precaution."""

        math_names = {
            k: v for k, v in math.__dict__.items() if not k.startswith("__")
        }

        code = compile(eqts.strip(), "<string>", "eval")
        harmful_input = [name for name in code.co_names if name not in math_names]

        if len(harmful_input) != 0:
            raise ValueError("Malicious equation", eqts)

        return eval(eqts, {"__builtins__": {}}, math_names)

    def get_telem_sample(self, sample_spec, buf):
        """Function get_telem_sample slices bits from buffer buf at the container offset
        and bit masking specified by sample_spec."""
        # read 8 bytes from buffer from offset and convert it to 64 bit little endian integer
        data = int.from_bytes(buf[int(sample_spec['offset']):int(sample_spec['offset']) + 8],
                              byteorder='little')
        # create mask
        msb_mask = 0xffffffffffffffff & ((2 ** (int(sample_spec['msb']) + 1)) - 1)
        lsb_mask = 0xffffffffffffffff & ((2 ** (int(sample_spec['lsb']))) - 1)
        mask = msb_mask & (~lsb_mask)
        # apply mask and shift right
        value = (data & mask) >> int(sample_spec['lsb'])
        return value

    def read_samples(self, uid, fname, add_sample_id=False):
        """Function read_samples reads telemetry file fname and decoded using PMT dictionary
        specified for UID uid. It returns a list of sample name value pairs. If add_sample_id is True
        sample id is added to sample name"""
        ret = {}
        buffer = ""
        if sys.platform == "linux":
            try:
                self.assert_is_not_symlink(fname)
                with open(fname, 'rb') as fd:
                    buffer = fd.read()
            except IOError:
                self.logger("Unable to read file %s." % fname)
                return ret
        elif sys.platform == "win32":
            telemetry = get_telemetry(fname, use_qwords=True)
            for t in telemetry:
                if str(hex(t['guid'])) in uid:
                    buffer = t['data']

        parsed_samples = {}

        for metric in self.pmt[uid]['samples']:
            t = self.pmt[uid]['samples'][metric]
            parsed_samples[metric] = self.get_telem_sample(t, buffer)

        for metric in self.pmt[uid]['transformations_mapping']:
            t = {}

            if len(self.conf["ALLOWLIST"]) != 0:
                metric_name = metric.split(".")[1]
                if not any([re.match(allowed_metric, metric_name) for allowed_metric in self.conf["ALLOWLIST"]]):
                    continue

            tm = self.pmt[uid]['transformations_mapping'][metric]
            tt = self.pmt[uid]['transformations'][tm['transformREF']]
            t["sampleName"] = tm["sampleName"]
            t["datatypeID"] = tm["datatypeID"]
            t["sampleID"] = tm["sampleID"]
            dt = self.pmt[uid]['datatypes'][t['datatypeID']]
            if 'units' in dt:
                try:
                    t['unit'] = dt['units']['symbol']
                except KeyError:
                    t['unit'] = ""
            else:
                t['unit'] = ""

            t['transform_name'] = tm['transformREF']
            # initial transformation
            tf = tt['transform'].replace("$", "")
            tv = tf
            for p in tm['inputs']:
                sn = tm['inputs'][p]
                tf = tf.replace(p, sn)
                tv = tv.replace(p, str(parsed_samples[sn]))
            t['inputs'] = tm['inputs']
            t['transform_formula'] = tf
            t['transform_value'] = tv

            try:
                t['value'] = self.safe_eval(tv)
            except Exception:
                # Ignore failed equation evaluations
                continue
            if add_sample_id:
                ret[f"{t['sampleName']}_{t['sampleID']}"] = t['value']
            else:
                ret[t['sampleName']] = t['value']
        return ret

    def read(self):
        """Collectd read callback."""
        for uid, files in self.pmt_files.items():
            for idx, fname in enumerate(files):
                t_ret = self.read_samples(uid, fname)
                for sample_name in t_ret.keys():
                    sample_value = t_ret[sample_name]
                    tm = self.pmt[uid]['transformations_mapping'][sample_name]
                    samp_type = 'gauge' if tm['SampleType'] == 'Snapshot' else 'counter'
                    sn = sample_name.lower().split('.')[0].replace('[', '.').replace(']', '')
                    ti = sample_name.lower().split('.')[1]
                    if ti == 'cntr_reserved' or ti == 'smpl_reserved':
                        continue
                    ti = ti.replace('[', '.').replace(']', '')

                    # Add to collectd values
                    collectd.Values(plugin="pmt." + str(idx),
                                    plugin_instance=sn,
                                    type_instance=ti,
                                    type=samp_type,
                                    values=[sample_value]).dispatch()

    def shutdown(self):
        """Collectd plugin shutdown callback."""
        pass

    def flush(self, timeout, identifier):
        """Collectd plugin flush callback."""
        pass

    def periodic_readsamples(self, event, add_sample_id=False):
        """Method used to read PMT data and reschedule next read.
         If add_sample_id is True sample id is added to PMT data"""
        ep_time = int(time.time())
        result = ""
        fmt = "pmt.{}.{}.{} {} {}\n"
        # print(self.pmt_files)
        for uid in self.pmt_files.keys():
            files = self.pmt_files[uid]
            for idx, fname in enumerate(files):
                t_ret = self.read_samples(uid, fname, add_sample_id)
                for s_name, s_value in t_ret.items():
                    sn = s_name.lower().replace('[', '.').replace(']', '')
                    result += fmt.format(platform.uname()[1], idx, sn, s_value, ep_time)

        # There are use cases, when agent is executed manually and output is piped to the STDOUT to Graphite server.
        # Log INFO cannot be piped, so that's a workaround.
        try:
            if logging.getLogger().handlers[0].baseFilename != "":
                logging.log(msg=result, level=logging.INFO)
            else:
                print(result)
        except AttributeError:
            print(result)

        if event is not None:
            event.set(sch.enter(self.interval, 1, self.periodic_readsamples, argument=(event, add_sample_id)))


class ScheduledEvent:
    """Helper class to allow pass-by-reference in sched module."""

    def __init__(self, event=None):
        self.set(event)

    def set(self, event):
        self.event = event


def file_lines_to_list(path):
    """Reads lines from given path and stores it as list"""
    lines = []
    try:
        url = urlparse(path)
        if url.scheme == "":
            with open(path) as file:
                lines = file.read().splitlines()
        else:
            with urllib.request.urlopen(path) as file:
                lines = file.read().decode('utf-8').splitlines()

    except Exception as e:
        raise argparse.ArgumentTypeError(
            f"Unable to read lines from given file: {e}")
    return lines


if __name__ != "__main__":
    # Initialize collectd plugin context.
    import collectd

    plugin = PmtPlugin(mode=PmtPlugin.COLLECTD)
    collectd.register_config(plugin.config)
    collectd.register_read(plugin.read)
    collectd.register_init(plugin.init)
    collectd.register_shutdown(plugin.shutdown)
    collectd.register_flush(plugin.flush)
else:
    # Stand-alone agent mode, reporting to stdout.
    import time
    import sched
    import logging
    import signal

    parser = argparse.ArgumentParser(description="PMT agent, reporting telemetry to stdout.")
    parser.add_argument("-s", required=True, dest='url',
                        help="PMT repository XML metadata", type=str)
    parser.add_argument("-i", required=False, dest='interval', type=int,
                        default=5, help="Interval between reads (in seconds).")
    parser.add_argument("-r", required=False, dest='read', help="Read metrics and exit", action="store_true")
    parser.add_argument("-a", required=False, dest='id', help="Append sampleID to sample identifier",
                        action="store_true")
    parser.add_argument("-w", required=False, default=['.*'], dest='allowlist',
                        help="Path to file containing allowed metrics in form of list of regular expressions "
                             "split by new line", type=file_lines_to_list)
    parser.add_argument("-o", required=False, dest='output_log_file',
                        help="Output log file. If file is not defined, logging is redirected to stdout", type=str)
    args = parser.parse_args()

    plugin = PmtPlugin(mode=PmtPlugin.AGENT, conf_url=args.url, interval=args.interval,
                       allowlist=args.allowlist)

    logging.basicConfig(filename=args.output_log_file, format='%(asctime)s %(levelname)s %(message)s',
                        level=logging.INFO)

    if not plugin.init():
        logging.error("Cannot initialize PMT agent. Exiting.")
        sys.exit(1)

    if args.read:
        plugin.periodic_readsamples(None, args.id)
        sys.exit(0)

    sch = sched.scheduler(time.time, time.sleep)
    schedule = ScheduledEvent()


    def sig_handler(sig, frame):
        """Signal handler to exit stand-alone mode."""
        try:
            sch.cancel(schedule.event)
        except Exception:
            pass
        sys.exit(0)


    signal.signal(signal.SIGINT, sig_handler)
    schedule.set(sch.enter(args.interval, 1, plugin.periodic_readsamples, argument=(schedule, args.id)))
    sch.run()
