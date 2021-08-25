# JSIsolate

JSIsolate is a system that provides an isolated and reliable JavaScript execution environment in the browser. It records JavaScript object accesses, and generates script isolation policies based on the accesses. It then enforces the policies by executing scripts in separate execution contexts.

In the released version, JSIsolate only isolate scripts in the main frames to improve the reliability of first-party JavaScript code.

JSIsolate is implemented on Chromium (version 71.0.3578.98) and has been tested on Debian 9.11 (stretch).

The repository has been archived [here](https://zenodo.org/record/5256913), with a DOI of __10.5281/zenodo.5256913__.

## Setup

Step 1: Set up the _binaries_ folder. We release the compiled binaries [here](https://zenodo.org/record/5255066), with a DOI of __10.5281/zenodo.5255066__. Please download the *.zip files, create a _binaries_ folder in the root folder, and put the unzipped folders in the _binaries_ folder first. The resulting directory should follow a structure of:

fse21-jsisolate-artifact/\
|
|--- python_scripts/\
|    |-- auto.sh\
|    |-- chromedriver\
|    |-- collect_logs.py\
|    \-- ... ...\
|\
|--- patch_files/\
│    |-- build.patch\
│    \-- ... ...\
|\
|--- binaries/\
|    |-- clean/\
|    |-- dump/\
|    \-- isolation/\
|\
|--- CONTACT.md\
|--- INSTALL.md\
|--- README.md\
|--- requirements.txt\
\--- ... ...

Step 2: Install necessary python modules and the chromedriver.

We provide the data analysis python scripts in folder *python_scripts*. All the scripts have been tested in __Python 3.5.3__. 

You need to install some python modules and the chromedriver (version 2.46.628388) as follows.

```shell
python3.5 -m pip install -r requirements.txt
sudo cp python_scripts/chromedriver /usr/local/bin
```

## Executables

We release the compiled binaries of JSIsolate, one for dumping object access logs (binaries/dump/chrome), one for enforcing script isolation (binaries/isolation/chrome), along with a Vanilla Chromium browser (binaries/clean/chrome).

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

### Log collection browser

```shell
cd binaries/dump
./chrome --no-sandbox
```

### Script isolation browser

```shell
# CONFIG_FILE: a json file that contains script isolation policies
# FALLBACK_CONTEXT: the fallback context ID to use when fail to find a script in the policies
# POLICY_MODE: 1 for domain-level policies and 0 for url-level policies

# domain.configs-simple is a sample domain-level policy file for http://www.google.com
# url.configs-simple is a sample URL-level policy file for http://www.google.com
# change CONFIG_FILE to a different one when testing different websites
cd binaries/isolation
CONFIG_FILE=domain.configs-simple FALLBACK_CONTEXT=1 POLICY_MODE=1 ./chrome --no-sandbox http://www.google.com
CONFIG_FILE=url.configs-simple FALLBACK_CONTEXT=1 POLICY_MODE=0 ./chrome --no-sandbox http://www.google.com
```

### Vanilla browser

```shell
cd binaries/clean
./chrome --no-sandbox
```

## Data Availability

We have released the object access logs and the script isolation policies generated by JSIsolate [here](https://zenodo.org/record/5242976), with a DOI of __10.5281/zenodo.5242976__.


## Data Collection

We provide our data collection script in the *python_scripts* folder.

You may change line 752 and 762 to adjust the timeout, e.g., if some website cannot finish loading within the timeout after multiple tries, enlarge the timeout to 360 and 320 in line 752 and 762, respectively.

You may comment line 852~854 (the monkey testing code) for computing log collection overhead.

```shell
cd python_scripts
python collect_logs.py -u iso -d [LOG_DIR] -s [START_RANK] -e [END_RANK] -p [NUM_PROCESS] -n [NUM_INSTANCE] --log_pass=0

# Example usage
python collect_logs.py -u iso -d jsisolate -s 1 -e 1000 -p 8 -n 128 --log_pass=0
```
The above command will collect logs on Alexa top 1K websites using 8 processes and 128 task splits. Collected log files will be saved in folder *jsisolate*.

For more information about the options, use:

```shell
cd python_scripts
python collect_logs.py --help
```


## Object Access Logs Format
The format of different log files are  described below.
We record all writes in JavaScript to a memory location and dump the logs in _[rank].[main/sub].[frame\_cnt].access_ (e.g., 1.main.0.access) files. 

* Object read logs: 
  - [R], [timestamp], [script\_ID], [receiver object], [property name], [frame\_ID]
* Object write logs:
  - [W], [timestamp], [script_ID], [receiver object], [property name], [write value], [frame\_ID]
* __Additional note:__ The above entries are separated by a special string: ",obj__dep,".

We record a map from script IDs to script URLs in _[rank].[main/sub].[frame\_cnt].id2url_ (e.g., 1.main.0.id2url) files.

* [script\_ID], [script\_URL], [frame_ID]
* __Additional note:__ The above entries in each log are separated by "\t". The script URL is empty for inline scripts, event listeners and code generated by eval().

We record a map from script IDs to their parent script IDs in _[rank].[main/sub].[frame\_cnt].id2parentid_ (e.g., 1.main.0.id2parentid) files.

* [script\_ID], [parent_script\_ID], [frame_URL]
* __Additional note:__ The above entries in each log are separated by "," (COMMA). The parent_script_ID is <null> for static scripts.

We record the URL of all frames (i.e., the main frame and all iframes) in _[rank].[main/sub].[frame\_cnt].frame_ (e.g., 1.main.0.frame) files.

* Main frame URL logs:
  - ["main"], [main\_frame\_URL], [timestamp]
* Iframe URL logs:
  - ["sub"], [iframe\_frame\_URL], [timestamp]
* __Additional note:__ The above entries in each log are separated by " " (SPACE).

We saved the source code of scripts in _[rank].[main/sub].[frame\_cnt].[script\_ID].script_ (e.g., 1.main.0.17.script) files.

* The first line of the file is the script URL and the frame ID (separated by "\t").
*  The rest are the source code of the script.

## Script Isolation Policies Format

The isolation policies are saved in [rank].configs and [rank].configs-simple files.

In particular, we try to generate two categories of policies. 1) The domain-level policies (i.e., if any script from one domain is assigned to the first-party context, then all scripts from the same domain are assigned to the first-party context), and 2) The URL-level policies.

Compared with the *.configs-simple files, the *.configs files additionally provide for each static script A from a third-party domain the information about: 1) first-party scripts read by A, 2) first-party scripts that read A. This facilitates developers to adjust the policies when necessary.

### *.configs files format

#### domain-level

```shell
{
    frame URL 0: [
    	{
    		"match": script URL,  # "https:" and "http:" removed
    		"read": {
    			# A list of scripts that the current script reads
    			# Empty list for scripts from the first-party domain
    			(frame ID 0, script ID 0): [
    				script ID 0, # ID of a script that the current script reads
    				read timestamp,
    				read value,
    				read type,
    				read identifier name,
					duplicate_flag # true if two scripts are both from 3rd-party domains, false otherwise
    			],
    			... ...
    		},
    		"read by": {
    			# A list of scripts that are read by the current script
    			# Empty list for scripts from the first-party domain
    			(frame ID 1, script ID 1): [
    				script ID, # ID of the current script
    				read timestamp,
    				read value,
    				read type,
    				read identifier name
					duplicate_flag # true if two scripts are both from 3rd-party domains, false otherwise
    			]
    		}
    		"script_id": script ID, # ID of the current script
    		"world_id": context ID # "1": first-party context, "3": third-party context, "both": library script, execute in both contexts
    	},
    	... ...
    ],
    frame URL 1: [
    	... ...
    ],
    ... ...
}
```

#### url-level

Same as the above.

### *.configs-simple files format

#### domain-level

```shell
{
	frame URL 0: {
		# context ID: "1": first-party context, "3": third-party context, "both": library script, execute in both contexts
		# script domain: if context ID is "both", we use the URL as the key
		script domain 0: context ID 0, 
		script domain 1: context ID 1,
		... ...
	},
	frame URL 1: {
		... ...
	},
	... ...
}
```

#### URL-level

```shell
{
	frame URL 0: {
		# context ID: "1": first-party context, "3": third-party context, "both": library script, execute in both contexts
		# script URL: "https:" and "http:" removed
		script URL 0: context ID 0, 
		script URL 1: context ID 1,
		... ...
	},
	frame URL 1: {
		... ...
	},
	... ...
}
```

Additionally, we report the conflicting writes we detected in [rank].conflicts files. This also helps developers to validate and adjust the isolation policies.

### Conflict Files Format

```shell
{
	frame ID 0: {
		# Identifier of object properties are in format: objectID.propertName
		conflicting identifier 0: [
			# A list of conflicting writes to identifier 0
			[
				conflict type, # "type" (type conflicts)/"value" (value conflicts)/"function" (duplicate function definitions)
				conflicting script ID 1, # one of IDs of conflicting scripts
				write timestamp 1,
				write value 1,
				write type 1,
				conflicting script ID 2,
				write timestamp 2,
				write value 2,
				write type 2
			],
			... ...
		],
		conflicting identifier 1: [
			... ...
		],
		... ...
	},
	frame ID 1: {
		... ...
	}
}
```


## Data Analysis

We provide the data analysis scripts in folder *python_scripts*. 
To fully automate the analysis, you may change *LOG_DIR* in *analysis.sh* to your local folder where you want to save the log files.
You can further configure *START*, *END*, *NUM\_PROCESSE*S and *NUM\_INSTANCES* in _auto.sh_. Then run:

```shell
cd python_scripts
./auto.sh
```

The above command will execute the following python scripts for reproducing our results step by step. You may comment some of them to avoid redoing some computation.

* collect.py: collect object access logs for generating isolation policies

  If some websites cannot finish loading within the timeout after multiple tries, you may enlarge the timeout to, e.g., 360 and 320 in line 752 and 762, respectively. In large-scale scripts, however, we recommend to use a small timeout to save some time.

* url_level_analyze_dependency.py: generate URL-level isolation policies

* domain_level_analyze_dependency.py: generate domain-level isolation policies

* get_stats.py: summarize the statistics about the isolation policies, e.g., how many scripts from the third-party scripts are assigned to the first-party context

* isolation_and_record_performance.py: launch JSIsolate in the policy enforcement mode and log the performance data

  If some websites cannot finish loading within the timeout after multiple tries, you may enlarge the timeout to, e.g., 360 and 320 in line 800 and 811, respectively. In large-scale scripts, however, we recommend to use a small timeout to save some time.

* compare_exception_nums.py: compare the JS exception numbers to evaluate the compatibility

* compute_isolation_overhead.py: compute the script isolation overhead

The following script is current commented. Uncomment it when measuring the log collection overhead.

* compute_collection_overhead.py: compute the log collection overhead 

For more information about the usage of any script, run: 

```shell
python [script_name] --help

# Example
python domain_level_analyze_dependency.py --help
```

## Known Issues

* Chromium version 71.0.3578.98 uses `Document::IsInDocumentWrite()` to check whether an element is injected by `document.write`.  It is a known issue that the function may return a wrong flag when `document.write` is called for multiple times.  To solve the problem, we hook the C++ implementation of `document.write`. Each time a call to `document.write` is captured, we record the start and end positions of the injected string in the whole HTML code. At the time a DOM element is parsed and constructed from an injected string, we check the position of the string, and match it with the positions logged in `document.write`. Upon finding a match, we identify an element dynamically created through `document.write`.

  Unfortunately, as Chromium follows a complex logic for tracking the string positions, sometimes we may fail to capture the precise start and end positions. Therefore, in rare cases, JSIsolate will misclassify a static script as a dynamic one, which may cause compatibility issues.

  Nevertheless, the problem is a known issue with Chromium (see chromium/src/third_party/blink/renderer/core/script/script_loader.cc line 400 in version 71.0.3578.98). And we observe very rare problematic cases, i.e., 1 (http://www.china.com.cn) out of the top 100. We leave this as a future work to fix the problem.

* JSIsolate maintains a map from script ID to context ID to help determine the context for dynamic scripts (based on their initiator scripts). To differentiate scripts with the same URL but loaded in different frames, it creates the map for each frame separately. This may cause some problem when a script creates another script in a different frame, as in this case the initiator script record will be missing from the map of the current frame. Nonetheless, we use JSIsolate to isolate scripts in main frames only. We plan to fix it in the future.

## Copyright Information
Copyright © 2021 The Chinese University of Hong Kong

### Additional Notes

Notice that some files in JSIsolate may carry their own copyright notices.
In particular, JSIsolate's code release contains modifications to source files from the Google Chromium project (https://www.chromium.org), which are distributed under their own original license.

## License
Check the LICENSE.md file.

## Contact ##

[Mingxue Zhang](https://zhangmx1997.github.io) <mxzhang@cse.cuhk.edu.hk>

[Wei Meng](https://www.cse.cuhk.edu.hk/~wei/) <wei@cse.cuhk.edu.hk>
