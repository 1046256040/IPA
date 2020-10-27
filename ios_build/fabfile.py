#!/usr/bin/env python
#coding=utf8

"""
fabfile
~~~~~~~~~~~~~~~~
要使用 fab 命令， 请在本地安装 Fabfile 2.1.x 及以上版本

ios打包自动化
1. achive
2. export
3. upload
"""

import os
import re
import random
import hashlib
import math
import base64
import shutil
import requests
import time
import string
import json
import plistlib

from invoke import task

curPath = os.getcwd()

def check_path(path):
    if os.path.exists(path):
        return True
    parent, _ = os.path.split(path)
    if check_path(parent):
        print('make dir ', path)
        os.mkdir(path)
        return True
    else:
        raise Exit('cannot create path::', path)
        
def copy_file(src, dst, md5=False):
    '''拷贝文件至目标文件，返回目标文件的全目录'''
    if not os.path.exists(src):
        return

    srcdir, srcname = os.path.split(src)
    dstdir, dstname = os.path.split(dst)
    check_path(dstdir)
    if md5:
        sha = file_md5(src)
        name_list = dstname.split('.')
        index_max = len(name_list) - 1
        new_name = '%s_%s.%s' % ('.'.join(name_list[0:index_max]), sha, name_list[index_max])
        dst = os.path.join(dstdir, new_name)
    shutil.copy(src, dst)
    return dst

def replaceConst(path, version, debugVersion):
    alllines = []
    with open(path, 'r', encoding='utf-8', errors='ignore') as file:
        alllines = file.readlines()
        file.close()
    
    with open(path, 'w+', encoding='utf-8', errors='ignore') as file:
        for eachline in alllines:
            a = re.sub('{{APP_VERSION}}', version, eachline)
            a = re.sub('{{DEBUG_VERSION}}', debugVersion, a)
            file.writelines(a)
        file.close()

def execall(cmd):
    print('execall::: ', cmd)
    return os.system(cmd)

class ArchiveInfo(object):
    """<?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
        <plist version="1.0">
        <dict>
            <key>ApplicationProperties</key>
            <dict>
                <key>ApplicationPath</key>
                <string>Applications/barrett.app</string>
                <key>CFBundleIdentifier</key>
                <string>com.sagi.barrett</string>
                <key>CFBundleShortVersionString</key>
                <string>1.0.7</string>
                <key>CFBundleVersion</key>
                <string>8</string>
                <key>SigningIdentity</key>
                <string>Apple Development: Haifeng Deng (WA6MJB2Y9P)</string>
                <key>Team</key>
                <string>5KRL6VS2Z2</string>
            </dict>
            <key>ArchiveVersion</key>
            <integer>2</integer>
            <key>CreationDate</key>
            <date>2020-01-06T16:19:57Z</date>
            <key>Name</key>
            <string>Unity-iPhone</string>
            <key>SchemeName</key>
            <string>Unity-iPhone</string>
        </dict>
        </plist>"""
    path_application = ""
    bundle_id = ""
    version_name = ""
    version_code = 0
    cert = ""
    team_id = ""
    scheme = ""

    def from_archive_path(self, archive_path):
        info_path = os.path.join(archive_path, "Info.plist")
        with open(info_path, "rb") as f:
            plist = plistlib.load(f)

        application_properties = plist.get("ApplicationProperties")
        self.scheme = plist.get("SchemeName")

        self.path_application = application_properties.get("ApplicationPath")
        self.bundle_id = application_properties.get("CFBundleIdentifier")
        self.version_name = application_properties.get("CFBundleShortVersionString")
        self.version_code = application_properties.get("CFBundleVersion")
        self.cert = application_properties.get("SigningIdentity")
        self.team_id = application_properties.get("Team")
    

class BuildConfig(object):
    CONFIG_JSON_PATH = "./config.json"

    path_project = ""
    path_project_ios = ""
    path_info_plist = ""

    build_types = None

    build_type = ""
    team_id = ""
    scheme = ""
    bundle_id = ""
    method = ""
    profile = ""
    cert = ""
    configuration = ""
    version_name = ""
    version_code = 0
    build_num = 0
    bitcode = False

    env = ""  # test / prod

    name_ipa = ""

    path_build = ""
    path_output = ""
    path_tmp = ""

    install_template = ""

    def set_base_config(self, project, build_num):
        self.path_project = project
        self.build_num = build_num

    def read_from_archive_info(self, archive_info, method):
        self.method = method
        # 遍历 buildTypes 获得 cert profile 参数
        self.scheme = archive_info.scheme
        self.bundle_id = archive_info.bundle_id
        self.version_name = archive_info.version_name
        self.version_code = archive_info.version_code

    def set_config(self, project, build_type, configuration, version_name, version_code, build_num, env):
        self.path_project = project
        self.build_type = build_type
        self.configuration = configuration
        self.version_name = version_name
        self.version_code = version_code
        self.build_num = build_num
        self.env = env

        self.path_output = os.path.join(self.path_project, "build")
        self.read_from_file()
        self.name_ipa = "_".join([self.bundle_id, self.version_name, str(self.build_num)]) + ".ipa"
        

    def read_from_file(self):
        path_config = os.path.join(self.path_project, self.CONFIG_JSON_PATH)

        if not os.path.exists(path_config):
            print('没有配置文件:' + path_config)
            return False

        with open(path_config, 'r') as f:
            json_obj = json.load(f)
            f.close()

        self.read_from_json(json_obj)

    def read_from_json(self, json_obj):
        ios_obj = json_obj.get("ios")
        if ios_obj is None:
            print('配置文件格式错误')
            return

        path_ios = ios_obj.get("project")
        path_info = ios_obj.get("info")
        scheme = ios_obj.get("scheme")
        install_template = ios_obj.get("installTemplate")
        build_types = ios_obj.get("buildTypes")
        build_type_obj = build_types.get(self.build_type)

        self.path_project_ios = os.path.join(self.path_project, path_ios)
        self.path_info_plist = os.path.join(self.path_project, path_info)
        self.scheme = scheme
        self.install_template = install_template
        self.team_id = build_type_obj.get("teamId")
        self.bundle_id = build_type_obj.get("bundleId")
        self.method = build_type_obj.get("method")
        self.profile = build_type_obj.get("profile")
        self.cert = build_type_obj.get("cert")
        self.bitcode = build_type_obj.get("bitcode", False)

    def get_derived_data_path(self):
        return os.path.join(self.path_output, "tmp", str(self.build_num))

    def get_export_path(self):
        return os.path.join(self.path_output, str(self.build_num))

    def get_export_plist_path(self):
        return os.path.join(self.path_output, "tmp", str(self.build_num), self.bundle_id)

    def get_method(self):
        return self.method

    def generate_system_archive_path(self):
        """
        获得系统的 archive 文件夹,这样使用命令行导出后,在 xcode organizer 窗口一样可以看到
        :return:
        """
        username = os.environ.get('USER')
        group_dir = "_".join([self.bundle_id, self.version_name])
        filename = "_".join([self.bundle_id, self.version_name, str(self.build_num)])
        archive_path = "/Users/{username}/Library/Developer/Xcode/Archives/{group_dir}/{filename}.xcarchive".format(**locals())
        return archive_path

    def __str__(self):
        values = []
        for name, value in vars(self).items():
            values.append('%s=%s' % (name, value))

        return "\n".join(values)


class BuildToolIOS(object):
    build_config = None
    quiet = False
    dry = False

    def __init__(self, build_config, quiet, dry):
        self.build_config = build_config
        self.quiet = quiet
        self.dry = dry

    def ios_archive(self):
        code_sign_identity = self.build_config.cert
        provisioning_profile = self.build_config.profile

        project_path = self.build_config.path_project_ios
        scheme = self.build_config.scheme
        archive_path = self.build_config.generate_system_archive_path()
        derived_data_path = self.build_config.get_derived_data_path()
        configuration = self.build_config.configuration

        if project_path.endswith(".xcworkspace"):
            cmds = [
                "xcodebuild",
                "archive",
                "-workspace", project_path,
                "-scheme", scheme,
                "-archivePath", archive_path,
                "-configuration", configuration,
                "-derivedDataPath", derived_data_path,
            ]
        else:
            cmds = [
                "xcodebuild",
                "archive",
                "-project", project_path,
                "-scheme", scheme,
                "-archivePath", archive_path,
                "-configuration", configuration,
                "-derivedDataPath", derived_data_path,
            ]

        if code_sign_identity and provisioning_profile:
            cmds.append("CODE_SIGN_IDENTITY='{code_sign_identity}'".format(**locals()))
            cmds.append("PROVISIONING_PROFILE={provisioning_profile}".format(**locals()))
            cmds.append("CODE_SIGN_STYLE=Manual")

        cmd = " ".join(cmds)
        
        self.run_print_result(cmd)
        return archive_path

    def ios_archive_export(self, archive_path, archive_info, export_path, method):
        """
        导出 archive
        :return path_ipa
        """

        archive_path = archive_path or ""
        export_path = export_path or ""

        scheme = archive_info.scheme
        version_name = archive_info.version_name
        version_code = archive_info.version_code

        export_plist_path = self.create_export_plist(method)

        cmds = [
            "xcodebuild",
            "-exportArchive",
            "-archivePath", archive_path,
            "-exportPath", export_path,
            "-exportOptionsPlist", export_plist_path
        ]
        cmd = " ".join(cmds)
        print(cmd)
        self.run_print_result(cmd)
        return os.path.join(export_path, scheme + ".ipa")

    def create_export_plist(self, method):
        plist_path = self.build_config.get_export_plist_path()
        plist_file = os.path.join(plist_path, 'export.plist')
        plist_dict = {
            "teamID": self.build_config.team_id,
            "signingCertificate": self.build_config.cert,
            "provisioningProfiles": {
                self.build_config.bundle_id: self.build_config.profile
            },
            "method": method,
            "compileBitcode": True
        }
        if os.path.exists(plist_file):
            os.remove(plist_file)

        check_path(plist_path)
        with open(plist_file, "wb+") as f:
            plistlib.dump(plist_dict, f)
            f.close()

        return plist_file

    def clean(self):
        if os.path.exists(self.ipaPath):
            os.remove(self.ipaPath)
        if os.path.exists(self.tmpPath):
            cmds = [
                "rm",
                "-rf",
                self.tmpPath,
            ]
            if self.__execute(cmds) == 0:
                print('Clean temp dir success')
        if os.path.exists(self.build_path):
            cmds = [
                "rm",
                "-rf",
                self.build_path,
            ]
            if self.__execute(cmds) == 0:
                print('Clean dirs success')

    def archive(self):
        self.__prepare()
        archivePath = self.savePath + '/' + self.scheme + '.xcarchive'
        if os.path.exists(archivePath):
            subprocess.call(['rm', '-rf', archivePath])

        print('use scheme: %s' % self.scheme)
        print('use configuration: %s' % self.configuration)
        cmds = [
            'xcodebuild',
            'archive',
            "-scheme", self.scheme,
            "-configuration", self.configuration,
            "-derivedDataPath", self.build_path,
            "-archivePath", archivePath,
        ]
        if self.workspaceFile:
            cmds.append('-workspace')
            cmds.append(self.workspaceFile)
        if len(self.provisioning_profile_uuid) > 0:
            cmds.append("PROVISIONING_PROFILE_SPECIFIER=" + self.provisioning_profile_uuid)
        if len(self.certification_name) > 0:
            cmds.append("CODE_SIGN_IDENTITY=" + self.certification_name)
        if self.team_id:
            cmds.append("DEVELOPMENT_TEAM=" + self.team_id)
        if len(self.provisioning_profile_uuid) > 0 or len(self.certification_name) > 0 or self.team_id:
            cmds.append("CODE_SIGN_STYLE=Manual")
        if self.__execute(cmds) == 0:
            print("Archive project success!")

    def run_cmd(self, cmd):
        """
        运行脚本
        :return:
        """
        if not self.dry:
            return os.popen(cmd)

    def run_get_result(self, cmd):
        pipe = self.run_cmd(cmd)
        return pipe.read()

    def run_print_result(self, cmd):
        print("run:" + cmd)
        pipe = self.run_cmd(cmd)

        if not self.dry:
            while pipe and True:
                try:
                    line = pipe.readline()
                    if line:
                        print(line)
                    else:
                        break
                except Exception as e:
                    print(str(e))
                    pass
                    
    
# 打包build
@task(help={
    'dry': '是否只输出命令，但不真正执行',
    'quiet': '静默执行',
    'project': '工程路径',
    'buildNum': 'build_num',
    'buildType': 'build_type',
    'configuration': 'configuration',
    'versionName': 'version_name', 
    'versionCode': 'version_code', 
    'env': 'test|prod',
    'upload': '是否上传'})
def build(context, dry=True, quiet=True, project='', buildNum=0, buildType='test', configuration='release', versionName='1.0.0', versionCode=0, env='test', upload=True):
    build_config = BuildConfig()
    build_config.set_config(
        project,
        buildType,
        configuration,
        versionName,
        versionCode,
        buildNum,
        env
    )
    
    print("打包配置:" + str(build_config))

    build_tool = BuildToolIOS(build_config, quiet, dry)
    archive_path = build_tool.ios_archive()
    
    archive_info = ArchiveInfo()
    archive_info.from_archive_path(archive_path)
    
    export_path = build_config.get_export_path()
    ipa_path =  build_tool.ios_archive_export(archive_path, archive_info, export_path, build_config.get_method())
    
    # print("ipa输出路径:", ipa_path)
    
    # if upload:
    #    print('上传ipa到cdn')
    

# 上传ipa到cdn    
@task(help={'version': 'App版本号', 'debugVersion': 'debug版本号', 'upload': '是否上传'})
def upload(context, version='1.0.0', debugVersion='1', upload=True):
    path = os.path.join(curPath, version, 'debug' + debugVersion)
    check_path(path)
    
    copy_file(os.path.join(curPath, 'template/upload', 'manifest.plist'), os.path.join(path, 'manifest.plist'))
    copy_file(os.path.join(curPath, 'template/upload', 'app.png'), os.path.join(path, 'app.png'))
    copy_file(os.path.join(curPath, 'template/upload', 'index.html'), os.path.join(path, 'index.html'))
    copy_file(os.path.join(curPath, 'template/upload', 'basketball-mobile.ipa'), os.path.join(path, 'basketball-mobile.ipa'))
    
    replaceConst(os.path.join(path, 'manifest.plist'), version, debugVersion)
    replaceConst(os.path.join(path, 'index.html'), version, debugVersion)
    
    if upload:
        execall('upx logout')
        execall('upx login sagih5 sagih5 H0e4JzvGCRc1Jdtz')
    
        local_path = path
        if local_path.endswith('/'):
            local_path = local_path[0:len(local_path) - 1]
        
        remote_path = '/basketball/ios/' + version + '/debug' + debugVersion
        
        print('============== 开始上传远程资源 ==============')
        if execall('upx sync %s %s' % (local_path, remote_path)):
            raise Exit('上传远程资源失败!')
        else:
            print('============== 上传远程资源完成 ==============')
        
    
