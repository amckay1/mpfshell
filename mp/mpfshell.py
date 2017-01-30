##
# The MIT License (MIT)
#
# Copyright (c) 2016 Stefan Wendler
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
##


import io
import cmd
import os
import argparse
import colorama
import glob
import platform
import sys
import serial
import logging

from mp import version
from mp.mpfexp import MpFileExplorer
from mp.mpfexp import MpFileExplorerCaching
from mp.mpfexp import RemoteIOError
from mp.pyboard import PyboardError
from mp.conbase import ConError
from mp.tokenizer import Tokenizer


class MpFileShell(cmd.Cmd):

    def __init__(self, color=False, caching=False, reset=False):
        if color:
            colorama.init()
            cmd.Cmd.__init__(self, stdout=colorama.initialise.wrapped_stdout)
        else:
            cmd.Cmd.__init__(self)
        self.use_rawinput = False

        self.color = color
        self.caching = caching
        self.reset = reset

        self.fe = None
        self.repl = None
        self.tokenizer = Tokenizer()

        self.__intro()
        self.__set_prompt_path()

    def __del__(self):
        self.__disconnect()

    def __intro(self):

        if self.color:
            self.intro = '\n' + colorama.Fore.GREEN + \
                         '** Micropython File Shell v%s, sw@kaltpost.de ** ' % version.FULL + \
                         colorama.Fore.RESET + '\n'
        else:
            self.intro = '\n** Micropython File Shell v%s, sw@kaltpost.de **\n' % version.FULL

        self.intro += '-- Running on Python %d.%d using PySerial %s --\n' \
                       % (sys.version_info[0], sys.version_info[1], serial.VERSION)

    def __set_prompt_path(self):

        if self.fe is not None:
            pwd = self.fe.pwd()
        else:
            pwd = "/"

        if self.color:
            self.prompt = colorama.Fore.BLUE + "mpfs [" + \
                          colorama.Fore.YELLOW + pwd + \
                          colorama.Fore.BLUE + "]> " + colorama.Fore.RESET
        else:
            self.prompt = "mpfs [" + pwd + "]> "

    def __error(self, msg):

        if self.color:
            print('\n' + colorama.Fore.RED + msg + colorama.Fore.RESET + '\n')
        else:
            print('\n' + msg + '\n')

    def __connect(self, port):

        try:
            self.__disconnect()

            if self.reset:
                print("Hard resetting device ...")
            if self.caching:
                self.fe = MpFileExplorerCaching(port, self.reset)
            else:
                self.fe = MpFileExplorer(port, self.reset)
            print("Connected to %s" % self.fe.sysname)
        except PyboardError as e:
            logging.error(e)
            self.__error(str(e))
        except ConError as e:
            logging.error(e)
            self.__error("Failed to open: %s" % port)
        except AttributeError as e:
            logging.error(e)
            self.__error("Failed to open: %s" % port)

    def __disconnect(self):

        if self.fe is not None:
            try:
                self.fe.close()
                self.fe = None
                self.__set_prompt_path()
            except RemoteIOError as e:
                self.__error(str(e))

    def __is_open(self):

        if self.fe is None:
            self.__error("Not connected to device. Use 'open' first.")
            return False

        return True

    def __parse_file_names(self, args):

        tokens, rest = self.tokenizer.tokenize(args)

        if rest != '':
            self.__error("Invalid filename given: %s" % rest)
        else:
            return [token.value for token in tokens]

        return None

    def do_exit(self, args):
        """exit
        Exit this shell.
        """
        self.__disconnect()

        return True

    do_EOF = do_exit

    def do_open(self, args):
        """open <TARGET>
        Open connection to device with given target. TARGET might be:

        - a serial port, e.g.       ttyUSB0, ser:/dev/ttyUSB0
        - a telnet host, e.g        tn:192.168.1.1 or tn:192.168.1.1,login,passwd
        - a websocket host, e.g.    ws:192.168.1.1 or ws:192.168.1.1,passwd
        """

        if not len(args):
            self.__error("Missing argument: <TARGET>")
        else:
            if not args.startswith("ser:/dev/") \
                    and not args.startswith("ser:COM") \
                    and not args.startswith("tn:") \
                    and not args.startswith("ws:"):

                if platform.system() == "Windows":
                    args = "ser:" + args
                else:
                    args = "ser:/dev/" + args

            self.__connect(args)

    def complete_open(self, *args):
        ports = glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*')
        return [i[5:] for i in ports if i[5:].startswith(args[0])]

    def do_close(self, args):
        """close
        Close connection to device.
        """

        self.__disconnect()

    def do_ls(self, directory):
        """ls [directory]
        List remote files, optionally in directory
        """

        if self.__is_open():
            olddir = self.fe.pwd()
            try:
                if len(directory)!=0:
                    self.fe.cd(directory)
                    
                files = self.fe.ls(add_details=True)

                if self.fe.pwd() != "/":
                    files = [("..", "D")] + files

                print("\nRemote files in '%s':\n" % self.fe.pwd())

                # Sort alphabetically, then sort folders over files
                files = sorted(sorted(files,key=lambda file: file[0]), key=lambda file: file[1])

                for elem, type in files:
                    if type == 'F':
                        if self.color:
                            print(colorama.Fore.CYAN + ("       %s" % elem) + colorama.Fore.RESET)
                        else:
                            print("       %s" % elem)
                    else:
                        if self.color:
                            print(colorama.Fore.MAGENTA + (" <dir> %s" % elem) + colorama.Fore.RESET)
                        else:
                            print(" <dir> %s" % elem)

                print("")

            except IOError as e:
                self.__error(str(e))

            if len(directory)!=0:
                self.fe.cd(olddir)

    def do_tree(self, directory):
        """tree [directory]
        List remote files recursively, optionally in directory
        """

        if self.__is_open():
            olddir = self.fe.pwd()
            if len(directory)!=0:
                self.fe.cd(directory)
            else:
                directory = self.fe.pwd()

            self.rec_tree(directory)

            if len(directory)!=0:
                self.fe.cd(olddir)
    def rec_tree(self,directory,prefix=""):
        try:
            olddir = self.fe.pwd()
            self.fe.cd(directory)
            files = self.fe.ls(add_details=True)
            if self.color:
                print(colorama.Fore.MAGENTA + ("%s%s" % (prefix, self.fe.pwd().split("/")[-1])) + colorama.Fore.RESET)
            else:
                print("%s%s" % (prefix, self.fe.pwd().split("/")[-1]))

            if len(prefix)>=4:
                if prefix[-4]=='└':
                    prefix = prefix[:-4]+' '*4
            files = sorted(sorted(files,key=lambda file: file[0]), key=lambda file: file[1])

            i = 0
            for elem, type in files:
                if type == 'F':
                    if len(prefix)>=3:
                        fprefix = prefix[:-4]+(' ' if prefix[-4] == ' ' else '│' )+' '*3
                    else:
                        fprefix = prefix
                    if len(files)==i+1:
                        fprefix = fprefix+"└── "
                    else:
                        fprefix = fprefix+"├── "
                        
                    if self.color:
                        print(colorama.Fore.CYAN + ("%s%s" % (fprefix, elem)) + colorama.Fore.RESET)
                    else:
                        print("%s%s" % (fprefix, elem))
                else:
                    if len(files)==i+1:
                        self.rec_tree(self.fe._fqn(elem),prefix+"└── ")
                    else:
                        self.rec_tree(self.fe._fqn(elem),prefix+"├── ")
                i+=1
            self.fe.cd(olddir)

        except IOError as e:
            self.__error(str(e))
    def do_pwd(self, args):
        """pwd
         Print current remote directory.
         """
        if self.__is_open():
            print(self.fe.pwd())

    def do_cd(self, args):
        """cd <TARGET DIR>
        Change current remote directory to given target.
        """
        if not len(args):
            self.__error("Missing argument: <REMOTE DIR>")
        elif self.__is_open():
            try:
                s_args = self.__parse_file_names(args)
                if not s_args:
                    return
                elif len(s_args) > 1:
                    self.__error("Only one argument allowed: <REMOTE DIR>")
                    return

                self.fe.cd(s_args[0])
                self.__set_prompt_path()
            except IOError as e:
                self.__error(str(e))
            except RemoteIOError as e:
                self.__error(str(e))

    def complete_cd(self, *args):

        try:
            files = self.fe.ls(add_files=False)
        except Exception:
            files = []

        return [i for i in files if i.startswith(args[0])]

    def do_md(self, args):
        """md <TARGET DIR>
        Create new remote directory.
        """
        if not len(args):
            self.__error("Missing argument: <REMOTE DIR>")
        elif self.__is_open():
            try:
                s_args = self.__parse_file_names(args)
                if not s_args:
                    return
                elif len(s_args) > 1:
                    self.__error("Only one argument allowed: <REMOTE DIR>")
                    return

                self.fe.md(s_args[0])
            except IOError as e:
                self.__error(str(e))

    def do_lls(self, args):
        """lls
        List files in current local directory.
        """

        files = os.listdir(".")

        print("\nLocal files:\n")

        for f in files:
            if os.path.isdir(f):
                if self.color:
                    print(colorama.Fore.MAGENTA + (" <dir> %s" % f) + colorama.Fore.RESET)
                else:
                    print(" <dir> %s" % f)
        for f in files:
            if os.path.isfile(f):
                if self.color:
                    print(colorama.Fore.CYAN + ("       %s" % f) + colorama.Fore.RESET)
                else:
                    print("       %s" % f)
        print("")

    def do_lcd(self, args):
        """lcd <TARGET DIR>
        Change current local directory to given target.
        """

        if not len(args):
            self.__error("Missing argument: <LOCAL DIR>")
        else:
            try:
                s_args = self.__parse_file_names(args)
                if not s_args:
                    return
                elif len(s_args) > 1:
                    self.__error("Only one argument allowed: <LOCAL DIR>")
                    return

                os.chdir(s_args[0])
            except OSError as e:
                self.__error(str(e).split("] ")[-1])

    def complete_lcd(self, *args):
        dirs = [o for o in os.listdir(".") if os.path.isdir(os.path.join(".", o))]
        return [i for i in dirs if i.startswith(args[0])]

    def do_lpwd(self, args):
        """lpwd
        Print current local directory.
        """

        print(os.getcwd())

    def do_put(self, args):
        """put <LOCAL FILE> [<REMOTE FILE>]
        Upload local file. If the second parameter is given,
        its value is used for the remote file name. Otherwise the
        remote file will be named the same as the local file.
        """

        if not len(args):
            self.__error("Missing arguments: <LOCAL FILE> [<REMOTE FILE>]")

        elif self.__is_open():

            s_args = self.__parse_file_names(args)
            if not s_args:
                return
            elif len(s_args) > 2:
                self.__error("Only one ore two arguments allowed: <LOCAL FILE> [<REMOTE FILE>]")
                return

            try:
                self.fe.put(src=s_args[0], dst=(s_args[1] if len(s_args)>1 else None))
            except IOError as e:
                self.__error(str(e))

    def do_putr(self, args):
        """putr <LOCAL DIRECTORY> [<REMOTE DIRECTORY>]
        Upload local directory recursively. If the second parameter is given,
        its value is used for the remote directory name. Otherwise the
        remote directory will be named the same as the local directory.
        """

        if not len(args):
            self.__error("Missing arguments: <LOCAL DIRECTORY> [<REMOTE DIRECTORY>]")

        elif self.__is_open():

            s_args = self.__parse_file_names(args)
            if not s_args:
                return
            elif len(s_args) > 2:
                self.__error("Only one ore two arguments allowed: <LOCAL DIRECTORY> [<REMOTE DIRECTORY>]")
                return

            try:
                self.fe.putr(src=s_args[0], dst=(s_args[1] if len(s_args)>1 else None))
            except IOError as e:
                self.__error(str(e))

    def complete_put(self, *args):
        files = [o for o in os.listdir(".") if os.path.isfile(os.path.join(".", o))]
        return [i for i in files if i.startswith(args[0])]

    def do_mput(self, args):
        """mput <SELECTION REGEX>
        Upload all local files that match the given regular expression.
        The remote files will be named the same as the local files.

        "mput" does not get directories, and it is note recursive.
        """

        if not len(args):
            self.__error("Missing argument: <SELECTION REGEX>")

        elif self.__is_open():

            try:
                self.fe.mput(os.getcwd(), args, True)
            except IOError as e:
                self.__error(str(e))

    def do_get(self, args):
        """get <REMOTE FILE> [<LOCAL FILE>]
        Download remote file. If the second parameter is given,
        its value is used for the local file name. Otherwise the
        locale file will be named the same as the remote file.
        """

        if not len(args):
            self.__error("Missing arguments: <REMOTE FILE> [<LOCAL FILE>]")

        elif self.__is_open():

            s_args = self.__parse_file_names(args)
            if not s_args:
                return
            elif len(s_args) > 2:
                self.__error("Only one ore two arguments allowed: <REMOTE FILE> [<LOCAL FILE>]")
                return

            try:
                self.fe.get(src=s_args[0], dst=(s_args[1] if len(s_args)>1 else None))
            except IOError as e:
                self.__error(str(e))

    def do_getr(self,args):
        """get <REMOTE DIRECTORY> [<LOCAL DIRECTORY>]
        Download remote directory recursively. If the second parameter is given,
        its value is used for the local directory name. Otherwise the
        locale directory will be named the same as the remote directory.
        """
        if not len(args):
            self.__error("Missing arguments: <REMOTE DIRECTORY> [<LOCAL DIRECTORY>]")

        elif self.__is_open():

            s_args = self.__parse_file_names(args)
            if not s_args:
                return
            elif len(s_args) > 2:
                self.__error("Only one ore two arguments allowed: <REMOTE DIRECTORY> [<LOCAL DIRECTORY>]")
                return

            try:
                self.fe.getr(src=s_args[0], dst=(s_args[1] if len(s_args)>1 else None))
            except IOError as e:
                self.__error(str(e))

    def do_mget(self, args):
        """mget <SELECTION REGEX>
        Download all remote files that match the given regular expression.
        The local files will be named the same as the remote files.

        "mget" does not get directories, and it is note recursive.
        """

        if not len(args):
            self.__error("Missing argument: <SELECTION REGEX>")

        elif self.__is_open():

            try:
                self.fe.mget(os.getcwd(), args, True)
            except IOError as e:
                self.__error(str(e))

    def complete_get(self, *args):

        try:
            files = self.fe.ls(add_dirs=False)
        except Exception:
            files = []

        return [i for i in files if i.startswith(args[0])]

    def do_rm(self, args):
        """rm <REMOTE FILE>
        Delete a remote file or empty directory.

        Note: to delete directories recursively see rmr.
        """

        if not len(args):
            self.__error("Missing argument: <REMOTE FILE>")
        elif self.__is_open():

            s_args = self.__parse_file_names(args)
            if not s_args:
                return
            elif len(s_args) > 1:
                self.__error("Only one argument allowed: <REMOTE FILE>")
                return

            try:
                self.fe.rm(s_args[0])
            except IOError as e:
                self.__error(str(e))
            except PyboardError:
                self.__error("Unable to send request to %s" % self.fe.sysname)

    def do_rmr(self, args):
        """rm <REMOTE DIR>
        Delete a remote directory recursively.

        Note: to delete single files and empty directories see rm.
        """

        if not len(args):
            self.__error("Missing argument: <REMOTE DIRECTORY>")
        elif self.__is_open():

            s_args = self.__parse_file_names(args)
            if not s_args:
                return
            elif len(s_args) > 1:
                self.__error("Only one argument allowed: <REMOTE DIRECTORY>")
                return

            try:
                self.fe.rmr(s_args[0])
            except IOError as e:
                self.__error(str(e))
            except PyboardError:
                self.__error("Unable to send request to %s" % self.fe.sysname)

    def do_mrm(self, args):
        """mrm <SELECTION REGEX>
        Delete all remote files that match the given regular expression.

        "mrm" does not delete directories, and it is note recursive.
        """

        if not len(args):
            self.__error("Missing argument: <SELECTION REGEX>")

        elif self.__is_open():

            try:
                self.fe.mrm(args, True)
            except IOError as e:
                self.__error(str(e))

    def complete_rm(self, *args):

        try:
            files = self.fe.ls()
        except Exception:
            files = []

        return [i for i in files if i.startswith(args[0])]

    def do_cat(self, args):
        """cat <REMOTE FILE>
        Print the contents of a remote file.
        """

        if not len(args):
            self.__error("Missing argument: <REMOTE FILE>")
        elif self.__is_open():

            s_args = self.__parse_file_names(args)
            if not s_args:
                return
            elif len(s_args) > 1:
                self.__error("Only one argument allowed: <REMOTE FILE>")
                return

            try:
                print(self.fe.gets(s_args[0]))
            except IOError as e:
                self.__error(str(e))

    complete_cat = complete_get

    def do_exec(self, args):
        """exec <STATEMENT>
        Execute a Python statement on remote.
        """

        def data_consumer(data):
            data = str(data.decode('utf-8'))
            sys.stdout.write(data.strip("\x04"))

        if not len(args):
            self.__error("Missing argument: <STATEMENT>")
        elif self.__is_open():

            try:
                self.fe.exec_raw_no_follow(args + "\n")
                ret = self.fe.follow(None, data_consumer)

                if len(ret[-1]):
                    self.__error(ret[-1])

            except IOError as e:
                self.__error(str(e))
            except PyboardError as e:
                self.__error(str(e))

    def do_repl(self, args):
        """repl
        Enter Micropython REPL.
        """

        import serial

        ver = serial.VERSION.split(".")

        if int(ver[0]) < 2 or (int(ver[0]) == 2 and int(ver[1]) < 7):
            self.__error("REPL needs PySerial version >= 2.7, found %s" % serial.VERSION)
            return

        if self.__is_open():

            if self.repl is None:

                from mp.term import Term
                self.repl = Term(self.fe.con)

                if platform.system() == "Windows":
                    self.repl.exit_character = chr(0x11)
                else:
                    self.repl.exit_character = chr(0x1d)

                self.repl.raw = True
                self.repl.set_rx_encoding('UTF-8')
                self.repl.set_tx_encoding('UTF-8')

            else:
                self.repl.serial = self.fe.con

            self.fe.teardown()
            self.repl.start()

            if self.repl.exit_character == chr(0x11):
                print("\n*** Exit REPL with Ctrl+Q ***")
            else:
                print("\n*** Exit REPL with Ctrl+] ***")

            try:
                self.repl.join(True)
            except Exception:
                pass

            self.repl.console.cleanup()

            self.fe.setup()
            print("")

    def do_mpyc(self, args):
        """mpyc <LOCAL PYTHON FILE>
        Compile a Python file into byte-code by using mpy-cross (which needs to be in the path).
        The compiled file has the same name as the original file but with extension '.mpy'.
        """

        if not len(args):
            self.__error("Missing argument: <LOCAL FILE>")
        else:

            s_args = self.__parse_file_names(args)
            if not s_args:
                return
            elif len(s_args) > 1:
                self.__error("Only one argument allowed: <LOCAL FILE>")
                return

            try:
                self.fe.mpy_cross(s_args[0])
            except IOError as e:
                self.__error(str(e))

    #def do_crash(self, args):
    #    """crash
    #    Runs some test code which likely crashes
    #    """
    #    if self.__is_open():
    #        try:
    #            self.fe.crash()
    #        except IOError as e:
    #            self.__error(str(e))     

    def complete_mpyc(self, *args):
        files = [o for o in os.listdir(".") if (os.path.isfile(os.path.join(".", o)) and o.endswith(".py"))]
        return [i for i in files if i.startswith(args[0])]


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--command", help="execute given commands (separated by ;)", default=None, nargs="*")
    parser.add_argument("-s", "--script", help="execute commands from file", default=None)
    parser.add_argument("-n", "--noninteractive", help="non interactive mode (don't enter shell)",
                        action="store_true", default=False)

    parser.add_argument("--nocolor", help="disable color", action="store_true", default=False)
    parser.add_argument("--nocache", help="disable cache", action="store_true", default=False)

    parser.add_argument("--logfile", help="write log to file", default=None)
    parser.add_argument("--loglevel", help="loglevel (CRITICAL, ERROR, WARNING, INFO, DEBUG)", default="INFO")

    parser.add_argument("--reset", help="hard reset device via DTR (serial connection only)", action="store_true",
                        default=False)

    args = parser.parse_args()

    format = '%(asctime)s\t%(levelname)s\t%(message)s'

    if args.logfile is not None:
        logging.basicConfig(format=format, filename=args.logfile,level=args.loglevel)
    else:
        logging.basicConfig(format=format, level=logging.CRITICAL)

    logging.info('Micropython File Shell v%s started' % version.FULL)
    logging.info('Running on Python %d.%d using PySerial %s' \
              % (sys.version_info[0], sys.version_info[1], serial.VERSION))

    mpfs = MpFileShell(not args.nocolor, not args.nocache, args.reset)

    if args.command is not None:

        for cmd in ' '.join(args.command).split(';'):
            scmd = cmd.strip()
            if len(scmd) > 0 and not scmd.startswith('#'):
                mpfs.onecmd(scmd)

    elif args.script is not None:

        f = open(args.script, 'r')
        script = ""

        for line in f:

            sline = line.strip()

            if len(sline) > 0 and not sline.startswith('#'):
                script += sline + '\n'

        if sys.version_info < (3, 0):
            sys.stdin = io.StringIO(script.decode('utf-8'))
        else:
            sys.stdin = io.StringIO(script)

        mpfs.intro = ''
        mpfs.prompt = ''

    if not args.noninteractive:

        try:
            mpfs.cmdloop()
        except KeyboardInterrupt:
            print("")


if __name__ == '__main__':

    main()
