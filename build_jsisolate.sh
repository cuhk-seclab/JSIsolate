#!/bin/bash - 
# This script has been tested only on Debian. You are recommended to use a Debian-like Linux dist.

set -o nounset                              # Treat unset variables as an error

is_darwin=0
is_freebsd=0
is_linux=0
UNAME=$(uname)
case $UNAME in
    "Darwin") is_darwin=1;;
    "FreeBSD") is_freebsd=1;;
    "Linux") is_linux=1;;
esac

VERSION=71.0.3578.98
NTHREADS=32 # Number of *gclient sync* threads
TMPFS_SIZE=20G # Size of tmpfs in memory for build path. You need at least 20G memory for a DEBUG build.
FAILURE_THRESHOLD=64 # The build process stops until this number of jobs fail
PATCH_DIR=patch_files # Change this if you put the .patch files at a different directory
BUILD_DIR=clean # Change this if you want to build at a different directory

# HELP
print_help ()
{
  echo "Usage : ./build_jsisolate.sh options"
  echo "  e.g., ./build_jsisolate.sh --all"
  echo ""
  echo "options:"
  echo "  --help          print this message"
  echo "    please install the necessary development tools (depot_tools) first following the instructions at"
  echo "    https://chromium.googlesource.com/chromium/src/+/master/docs/linux_build_instructions.md#Install"
  echo ""
  echo "  --all           execute all the necessary steps automatically, from downloading the source code, to building Chromium;"
  echo "    you should only run with this option at most ONCE and ONLY when you have not downloaded the source code"
  echo ""
  echo "  --fetch         fetch the source files of chromium (version $VERSION) and check out to a custom local development branch"
  echo "  --sync          run gclient sync to synchronize all files with (version $VERSION)"
  echo "  --deps          install the dependencies including CCACHE"
  echo "    you have to install the necessary packages yourself if this step fails"
  echo ""
  echo "  --patch-clean   apply the patches in our repository to replace parts of the Chromium source for building the Vanilla browser"
  echo "  --build-clean   build the Vanilla browser"
  echo ""
  echo "  --patch-dump    apply the patches in our repository to replace parts of the Chromium source for building JSIsolate (log collection mode)"
  echo "  --build-dump    build JSIsolate (log collection mode)"
  echo ""
  echo "  --patch-isolation    apply the patches in our repository to replace parts of the Chromium source for building JSIsolate (policy enforcement mode)"
  echo "  --build-isolation    build JSIsolate (policy enforcement mode)"
} # ----------  end of function print_help ----------


# CHECK OUT CHROMIUM SRC
fetch_source ()
{
  git config --global core.precomposeUnicode true
  fetch --nohooks chromium
  cd $CHROMIUM/src
  git checkout -b dev $VERSION
} # ----------  end of function fetch_source ----------


# SYNC ALL FILES WITH THE CHECKOUT VERSION
gclient_sync ()
{
  gclient sync --with_branch_heads --jobs $NTHREADS
} # ----------  end of function gclient_sync ----------


# INSTALL BUILD DEPENDENCIES
install_deps ()
{
  if [ $is_darwin = 1 ]; then
    xcode-select --install # You can comment this line if you have installed XCode already
    if hash port 2>/dev/null; then
      sudo port install wget ccache docbook2X autoconf automake libtool
      sudo mkdir -p /usr/local/opt/lzo/lib/
      cd /usr/local/opt/lzo/lib/
      sudo ln -s /opt/local/lib/liblzo2.2.dylib . 2>/dev/null
    elif hash brew 2>/dev/null; then
      brew install wget ccache autoconf automake libtool
      echo ""
    else
      echo "Please install HomeBrew or MacPorts before you proceed!"
      exit 1
    fi

  elif [ $is_linux = 1 ]; then
    sudo apt-get install ccache
    echo ""
    cd $CHROMIUM/src
    sudo ./build/install-build-deps.sh --no-syms --no-arm --no-chromeos-fonts --no-nacl
  fi
} # ----------  end of function install_deps ----------


# RUN Chromium-specific hooks
run_hooks ()
{
  cd $CHROMIUM/src
  gclient runhooks
} # ----------  end of function run_hooks ----------


# CHECK OUT CUSTOM REPOSITORIES
apply_patch_isolation ()
{
  cd $CHROMIUM/src/third_party/blink/public/web && git clean -df && git checkout -- . && patch -p1 < $ROOT/$PATCH_DIR/isolation_blink_public.patch
  cd $CHROMIUM/src/third_party/blink/renderer && git clean -df && git checkout -- . && patch -p1 < $ROOT/$PATCH_DIR/isolation_blink_renderer.patch
  cd $CHROMIUM/src/v8 && git clean -df && git checkout -- . && patch -p1 < $ROOT/$PATCH_DIR/isolation_v8.patch
  cd $CHROMIUM/src/content && git clean -df && git checkout -- . && patch -p1 < $ROOT/$PATCH_DIR/isolation_content.patch
  cd $CHROMIUM/src/extensions && git clean -df && git checkout -- . && patch -p1 < $ROOT/$PATCH_DIR/isolation_extension.patch
  cd $CHROMIUM/src/build/config/compiler && git clean -df && git checkout -- . && patch -p1 < $ROOT/$PATCH_DIR/build.patch
  run_hooks
} # ----------  end of function apply_patch_isolation ----------

apply_patch_clean ()
{
  cd $CHROMIUM/src/content && git clean -df && git checkout -- . && patch -p1 < $ROOT/$PATCH_DIR/clean_content.patch
  cd $CHROMIUM/src/build/config/compiler && git clean -df && git checkout -- . && patch -p1 < $ROOT/$PATCH_DIR/build.patch
  run_hooks
} # ----------  end of function apply_patch_clean ----------

apply_patch_dump ()
{
  cd $CHROMIUM/src/third_party/blink/public/web && git clean -df && git checkout -- . && patch -p1 < $ROOT/$PATCH_DIR/dump_blink_public.patch
  cd $CHROMIUM/src/third_party/blink/renderer && git clean -df && git checkout -- . && patch -p1 < $ROOT/$PATCH_DIR/dump_blink_renderer.patch
  cd $CHROMIUM/src/v8 && git clean -df && git checkout -- . && patch -p1 < $ROOT/$PATCH_DIR/dump_v8.patch
  cd $CHROMIUM/src/content && git clean -df && git checkout -- . && patch -p1 < $ROOT/$PATCH_DIR/dump_content.patch
  cd $CHROMIUM/src/extensions && git clean -df && git checkout -- . && patch -p1 < $ROOT/$PATCH_DIR/dump_extension.patch
  cd $CHROMIUM/src/build/config/compiler && git clean -df && git checkout -- . && patch -p1 < $ROOT/$PATCH_DIR/build.patch
  run_hooks
} # ----------  end of function apply_patch_dump ----------

# BUILD
conf_local_build_clean ()
{
  BUILD_DIR=clean # Change this if you want to build at a different directory
  cd $CHROMIUM/src
  mkdir -p out/$BUILD_DIR
  gn gen out/$BUILD_DIR '--args=cc_wrapper="ccache" use_jumbo_build=true is_debug=false enable_nacl=false'
} # ----------  end of function conf_local_build_clean ----------

conf_local_build_dump ()
{
  BUILD_DIR=dump # Change this if you want to build at a different directory
  cd $CHROMIUM/src
  mkdir -p out/$BUILD_DIR
  gn gen out/$BUILD_DIR '--args=cc_wrapper="ccache" use_jumbo_build=true is_debug=false enable_nacl=false'
} # ----------  end of function conf_local_build_dump ----------

conf_local_build_isolation ()
{
  BUILD_DIR=isolation # Change this if you want to build at a different directory
  cd $CHROMIUM/src
  mkdir -p out/$BUILD_DIR
  gn gen out/$BUILD_DIR '--args=cc_wrapper="ccache" use_jumbo_build=true is_debug=false enable_nacl=false'
} # ----------  end of function conf_local_build_isolation ----------

build_clean ()
{
  conf_local_build_clean
  export CCACHE_BASEDIR=$CHROMIUM
  cd $CHROMIUM/src
  time autoninja -C out/$BUILD_DIR chrome
} # ----------  end of function build_clean ----------

build_isolation ()
{
  conf_local_build_isolation
  export CCACHE_BASEDIR=$CHROMIUM
  cd $CHROMIUM/src
  time autoninja -C out/$BUILD_DIR chrome
} # ----------  end of function build_isolation ----------

build_dump ()
{
  conf_local_build_dump
  export CCACHE_BASEDIR=$CHROMIUM
  cd $CHROMIUM/src
  time autoninja -C out/$BUILD_DIR chrome
} # ----------  end of function build_dump ----------


mkdir -p chromium
ROOT=$PWD
cd chromium
CHROMIUM=$PWD
export GCLIENT_PY3=0

if [ $# -gt 0 ]; then
  if [ "$1" != "" ] ; then
    case "$1" in
      --fetch|--sync|--deps|--patch-clean|--patch-isolation|--patch-dump|--build-clean|--build-isolation|--build-dump|--all|--help )
        if [ "$1" = "--fetch" ] || [ "$1" = "--all" ]; then
          fetch_source
        fi
        if [ "$1" = "--sync" ] || [ "$1" = "--all" ]; then
          gclient_sync
        fi
        if [ "$1" = "--deps" ] || [ "$1" = "--all" ]; then
          install_deps
        fi
        if [ "$1" = "--patch-clean" ] || [ "$1" = "--all" ]; then
          apply_patch_clean
        fi
        if [ "$1" = "--build-clean" ] || [ "$1" = "--all" ]; then
          build_clean
        fi
        if [ "$1" = "--patch-isolation" ] || [ "$1" = "--all" ]; then
          apply_patch_isolation
        fi
        if [ "$1" = "--build-isolation" ] || [ "$1" = "--all" ]; then
          build_isolation
        fi
        if [ "$1" = "--patch-dump" ] || [ "$1" = "--all" ]; then
          apply_patch_dump
        fi
        if [ "$1" = "--build-dump" ] || [ "$1" = "--all" ]; then
          build_dump
        fi
        if [ "$1" = "--help" ]; then
          print_help
        fi
        ;;
      *)
        echo "Your option "\"$1\"" is invalid"
        exit
        ;;

    esac    # --- end of case ---
  fi
else
  print_help
fi
