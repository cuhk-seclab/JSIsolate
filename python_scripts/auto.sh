#!/bin/bash - 
USER_DIR="iso"
LOG_DIR="$PWD/tmp" # Directory for object access logs
START=1            # Start rank (1~1M)
END=20             # End rank (1~1M)
NUM_PROCESSES=8    # Number of concurrent processes
NUM_INSTANCES=128  # Number of task splits, we used 128 in our large-scale experiments



# You can comment some of the commands below to avoid redoing some computation
# collect_logs.py can be executed for multiple times in case some websites cannot finish loading within the timeout
# If some websites cannot finish loading within timeout after multiple tries, consider enlarging the timeout to 360s 
date
echo python3.5 collect_logs.py -u $USER_DIR -d $LOG_DIR -s $START -e $END -n $NUM_INSTANCES -p $NUM_PROCESSES --log_pass=0
time python3.5 collect_logs.py -u $USER_DIR -d $LOG_DIR -s $START -e $END -n $NUM_INSTANCES -p $NUM_PROCESSES --log_pass=0

# Uncomment the following 7 lines if you want to compute the data collection overhead
#date
#echo python3.5 collect_logs.py -u $USER_DIR -d $LOG_DIR -s $START -e $END -n $NUM_INSTANCES -p $NUM_PROCESSES --log_pass=1
#time python3.5 collect_logs.py -u $USER_DIR -d $LOG_DIR -s $START -e $END -n $NUM_INSTANCES -p $NUM_PROCESSES --log_pass=1
#
#date
#echo python3.5 compute_collection_overhead.py -u $USER_DIR -d $LOG_DIR -s $START -e $END -o $LOG_DIR -n $NUM_INSTANCES
#time python3.5 compute_collection_overhead.py -u $USER_DIR -d $LOG_DIR -s $START -e $END -o $LOG_DIR -n $NUM_INSTANCES



date
echo python3.5 url_level_analyze_dependency.py -u $USER_DIR -d $LOG_DIR -s $START -e $END -n $NUM_INSTANCES 
time python3.5 url_level_analyze_dependency.py -u $USER_DIR -d $LOG_DIR -s $START -e $END -n $NUM_INSTANCES 

date
echo python3.5 domain_level_analyze_dependency.py -u $USER_DIR -d $LOG_DIR -s $START -e $END -n $NUM_INSTANCES 
time python3.5 domain_level_analyze_dependency.py -u $USER_DIR -d $LOG_DIR -s $START -e $END -n $NUM_INSTANCES 


CONFIGS_DIR="$LOG_DIR/domain-level-policies"
date 
echo python3.5 get_stats.py -u $USER_DIR -d $CONFIGS_DIR -s $START -e $END -n $NUM_INSTANCES -o $CONFIGS_DIR
time python3.5 get_stats.py -u $USER_DIR -d $CONFIGS_DIR -s $START -e $END -n $NUM_INSTANCES -o $CONFIGS_DIR


CONFIGS_DIR="$LOG_DIR/url-level-policies"
date 
echo python3.5 get_stats.py -u $USER_DIR -d $CONFIGS_DIR -s $START -e $END -n $NUM_INSTANCES -o $CONFIGS_DIR
time python3.5 get_stats.py -u $USER_DIR -d $CONFIGS_DIR -s $START -e $END -n $NUM_INSTANCES -o $CONFIGS_DIR



# Running too many processes concurrently might cause the performance to be very unstable, therefore, we use only 2 processes here
# domain-level policies, fallback context ID of "3"
NUM_PROCESSES=2 
CONFIGS_DIR="$LOG_DIR/domain-level-policies"
PROXY_LOG_DIR_PREFIX="$PWD/domain-fallback3-round"
CWD=$PWD
for cnt in {0..0}
do
  PROXY_LOG_DIR="$PROXY_LOG_DIR_PREFIX$cnt"
  rm -rf exps/*
  cd $CWD

  # If some websites cannot finish loading within timeout after multiple tries, consider enlarging the timeout to 360s 
  date
  echo python3.5 isolation_and_record_performance.py -u $USER_DIR -d $PROXY_LOG_DIR -s $START -e $END -c $CONFIGS_DIR -n $NUM_INSTANCES -p $NUM_PROCESSES --log_pass=3 --policy_mode=1
  time python3.5 isolation_and_record_performance.py -u $USER_DIR -d $PROXY_LOG_DIR -s $START -e $END -c $CONFIGS_DIR -n $NUM_INSTANCES -p $NUM_PROCESSES --log_pass=3 --policy_mode=1

  rm -rf exps/*
  cd $CWD
  sleep 10 # Use a small value for testing purpose. We used 120 in our large-scale experiments.

  date
  echo python3.5 isolation_and_record_performance.py -u $USER_DIR -d $PROXY_LOG_DIR -s $START -e $END -c $CONFIGS_DIR -n $NUM_INSTANCES -p $NUM_PROCESSES --log_pass=0
  time python3.5 isolation_and_record_performance.py -u $USER_DIR -d $PROXY_LOG_DIR -s $START -e $END -c $CONFIGS_DIR -n $NUM_INSTANCES -p $NUM_PROCESSES --log_pass=0

  rm -rf exps/*
  cd $CWD
  sleep 10

  date
  echo python3.5 compare_exception_nums.py -u $USER_DIR -d $PROXY_LOG_DIR -s $START -e $END -n $NUM_INSTANCES 
  time python3.5 compare_exception_nums.py -u $USER_DIR -d $PROXY_LOG_DIR -s $START -e $END -n $NUM_INSTANCES

  date
  echo python3.5 compute_isolation_overhead.py -u $USER_DIR -d $PROXY_LOG_DIR -s $START -e $END -o $PROXY_LOG_DIR -n $NUM_INSTANCES
  time python3.5 compute_isolation_overhead.py -u $USER_DIR -d $PROXY_LOG_DIR -s $START -e $END -o $PROXY_LOG_DIR -n $NUM_INSTANCES

  sleep 30 # Use a small value for testing purpose. We used 360 in our large-scale experiments.
done




# domain-level policies, fallback context ID of "1"
NUM_PROCESSES=2 
CONFIGS_DIR="$LOG_DIR/domain-level-policies"
PROXY_LOG_DIR_PREFIX="$PWD/domain-fallback1-round"
CWD=$PWD
for cnt in {0..0}
do
  PROXY_LOG_DIR="$PROXY_LOG_DIR_PREFIX$cnt"
  rm -rf exps/*
  cd $CWD

  date
  echo python3.5 isolation_and_record_performance.py -u $USER_DIR -d $PROXY_LOG_DIR -s $START -e $END -c $CONFIGS_DIR -n $NUM_INSTANCES -p $NUM_PROCESSES --log_pass=1 --policy_mode=1
  time python3.5 isolation_and_record_performance.py -u $USER_DIR -d $PROXY_LOG_DIR -s $START -e $END -c $CONFIGS_DIR -n $NUM_INSTANCES -p $NUM_PROCESSES --log_pass=1 --policy_mode=1

  rm -rf exps/*
  cd $CWD
  sleep 10

  date
  echo python3.5 isolation_and_record_performance.py -u $USER_DIR -d $PROXY_LOG_DIR -s $START -e $END -c $CONFIGS_DIR -n $NUM_INSTANCES -p $NUM_PROCESSES --log_pass=0
  time python3.5 isolation_and_record_performance.py -u $USER_DIR -d $PROXY_LOG_DIR -s $START -e $END -c $CONFIGS_DIR -n $NUM_INSTANCES -p $NUM_PROCESSES --log_pass=0

  rm -rf exps/*
  cd $CWD
  sleep 10

  date
  echo python3.5 compare_exception_nums.py -u $USER_DIR -d $PROXY_LOG_DIR -s $START -e $END -n $NUM_INSTANCES 
  time python3.5 compare_exception_nums.py -u $USER_DIR -d $PROXY_LOG_DIR -s $START -e $END -n $NUM_INSTANCES

  date
  echo python3.5 compute_isolation_overhead.py -u $USER_DIR -d $PROXY_LOG_DIR -s $START -e $END -o $PROXY_LOG_DIR -n $NUM_INSTANCES
  time python3.5 compute_isolation_overhead.py -u $USER_DIR -d $PROXY_LOG_DIR -s $START -e $END -o $PROXY_LOG_DIR -n $NUM_INSTANCES

  sleep 30
done




# URL-level policies, fallback context ID of "3"
NUM_PROCESSES=2 
CONFIGS_DIR="$LOG_DIR/url-level-policies"
PROXY_LOG_DIR_PREFIX="$PWD/url-fallback3-round"
CWD=$PWD
for cnt in {0..0}
do
  PROXY_LOG_DIR="$PROXY_LOG_DIR_PREFIX$cnt"
  rm -rf exps/*
  cd $CWD

  date
  echo python3.5 isolation_and_record_performance.py -u $USER_DIR -d $PROXY_LOG_DIR -s $START -e $END -c $CONFIGS_DIR -n $NUM_INSTANCES -p $NUM_PROCESSES --log_pass=3 --policy_mode=0
  time python3.5 isolation_and_record_performance.py -u $USER_DIR -d $PROXY_LOG_DIR -s $START -e $END -c $CONFIGS_DIR -n $NUM_INSTANCES -p $NUM_PROCESSES --log_pass=3 --policy_mode=0

  rm -rf exps/*
  cd $CWD
  sleep 10

  date
  echo python3.5 isolation_and_record_performance.py -u $USER_DIR -d $PROXY_LOG_DIR -s $START -e $END -c $CONFIGS_DIR -n $NUM_INSTANCES -p $NUM_PROCESSES --log_pass=0
  time python3.5 isolation_and_record_performance.py -u $USER_DIR -d $PROXY_LOG_DIR -s $START -e $END -c $CONFIGS_DIR -n $NUM_INSTANCES -p $NUM_PROCESSES --log_pass=0

  rm -rf exps/*
  cd $CWD
  sleep 10

  date
  echo python3.5 compare_exception_nums.py -u $USER_DIR -d $PROXY_LOG_DIR -s $START -e $END -n $NUM_INSTANCES 
  time python3.5 compare_exception_nums.py -u $USER_DIR -d $PROXY_LOG_DIR -s $START -e $END -n $NUM_INSTANCES

  date
  echo python3.5 compute_isolation_overhead.py -u $USER_DIR -d $PROXY_LOG_DIR -s $START -e $END -o $PROXY_LOG_DIR -n $NUM_INSTANCES
  time python3.5 compute_isolation_overhead.py -u $USER_DIR -d $PROXY_LOG_DIR -s $START -e $END -o $PROXY_LOG_DIR -n $NUM_INSTANCES

  sleep 30
done





# URL-level policies, fallback context ID of "1"
NUM_PROCESSES=2 
CONFIGS_DIR="$LOG_DIR/url-level-policies"
PROXY_LOG_DIR_PREFIX="$PWD/url-fallback1-round"
CWD=$PWD
for cnt in {0..0}
do
  PROXY_LOG_DIR="$PROXY_LOG_DIR_PREFIX$cnt"
  rm -rf exps/*
  cd $CWD

  date
  echo python3.5 isolation_and_record_performance.py -u $USER_DIR -d $PROXY_LOG_DIR -s $START -e $END -c $CONFIGS_DIR -n $NUM_INSTANCES -p $NUM_PROCESSES --log_pass=1 --policy_mode=0
  time python3.5 isolation_and_record_performance.py -u $USER_DIR -d $PROXY_LOG_DIR -s $START -e $END -c $CONFIGS_DIR -n $NUM_INSTANCES -p $NUM_PROCESSES --log_pass=1 --policy_mode=0

  rm -rf exps/*
  cd $CWD
  sleep 10

  date
  echo python3.5 isolation_and_record_performance.py -u $USER_DIR -d $PROXY_LOG_DIR -s $START -e $END -c $CONFIGS_DIR -n $NUM_INSTANCES -p $NUM_PROCESSES --log_pass=0
  time python3.5 isolation_and_record_performance.py -u $USER_DIR -d $PROXY_LOG_DIR -s $START -e $END -c $CONFIGS_DIR -n $NUM_INSTANCES -p $NUM_PROCESSES --log_pass=0

  rm -rf exps/*
  cd $CWD
  sleep 10

  date
  echo python3.5 compare_exception_nums.py -u $USER_DIR -d $PROXY_LOG_DIR -s $START -e $END -n $NUM_INSTANCES 
  time python3.5 compare_exception_nums.py -u $USER_DIR -d $PROXY_LOG_DIR -s $START -e $END -n $NUM_INSTANCES

  date
  echo python3.5 compute_isolation_overhead.py -u $USER_DIR -d $PROXY_LOG_DIR -s $START -e $END -o $PROXY_LOG_DIR -n $NUM_INSTANCES
  time python3.5 compute_isolation_overhead.py -u $USER_DIR -d $PROXY_LOG_DIR -s $START -e $END -o $PROXY_LOG_DIR -n $NUM_INSTANCES

  sleep 30
done

