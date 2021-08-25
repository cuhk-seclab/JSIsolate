# Installation instructions

## Setup 

We release the compiled binaries of JSIsolate, one for dumping object access logs (binaries/dump/chrome), one for enforcing script isolation (binaries/isolation/chrome), along with a Vanilla Chromium browser (binaries/clean/chrome). There is no need to install any software. Just unzip the *.zip files under _binaires_ and you can directly run the browsers as below.

We also release the patch files of our implementation in the _patch\_files_ folder. To compile the browsers from source code, use the commands below. Remember to move the compiled bianries to the _binaries_ folder as mentioned above.

```shell
# Install depot_tools
git clone https://chromium.googlesource.com/chromium/tools/depot_tools.git
export PATH=$PATH:/path/to/depot_tools

# Fetch source and build
./build_jsisolate.sh --all

# For more information, use:
./build_jsisolate.sh --help
```

All three browsers are of version 71.0.3578.98, and have been tested on Debian 9.11 (stretch).

## Data collection browser

```shell
cd binaries/dump
./chrome --no-sandbox
```

## Script isolation browser

```shell
# CONFIG_FILE: a json file that contains script isolation policies
# FALLBACK_CONTEXT: the fallback context ID to use when fail to find a script in the policies
# POLICY_MODE: 1 for domain-level policies and 0 for url-level policies

# domain.configs-simple is a sample domain-level policy file for http://www.google.com
# url.configs-simple is a sample URL-level policy file for http://www.google.com
# change CONFIG_FILE to a different one when testing different websites
cd binaries/isolation
CONFIG_FILE=domain.configs-simple FALLBACK_CONTEXT=1 POLICY_MODE=1 --no-sandbox http://www.google.com
CONFIG_FILE=url.configs-simple FALLBACK_CONTEXT=1 POLICY_MODE=0 --no-sandbox http://www.google.com
```

## Vanilla browser

```shell
cd binaries/clean
./chrome --no-sandbox
```
