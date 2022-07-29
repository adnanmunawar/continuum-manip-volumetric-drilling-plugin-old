#!/bin/bash

/home/henry/ambf/bin/lin-x86_64/ambf_simulator \
  --launch_file /home/henry/bigss/catkin_ws/src/continuum-manip-volumetric-drilling-plugin/launch.yaml \
  -l 24,25 \
  --csv_filename_static_traces /home/henry/bigss/catkin_ws/src/continuum-manip-volumetric-drilling-plugin/resources/goal_points.csv \
  --name_body_to_trace Burr \