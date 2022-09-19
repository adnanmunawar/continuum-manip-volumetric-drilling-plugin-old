#!/bin/bash

# /home/henry/ambf/bin/lin-x86_64/ambf_simulator \
#     --launch_file /home/henry/bigss/catkin_ws/src/continuum-manip-volumetric-drilling-plugin/launch.yaml \
#     -l 11,33,25,29,30 \
#     --name_body_to_trace Burr \
#     --anatomy_volume_name spine_seg \
#     --csv_filename_static_traces /home/henry/bigss/catkin_ws/src/continuum-manip-volumetric-drilling-plugin/resources/axis.csv


/home/bigss/ambf/bin/lin-x86_64/ambf_simulator \
    --launch_file /home/bigss/bigss/catkin_ws/src/continuum-manip-volumetric-drilling-plugin/launch.yaml \
    -l 11,15,25,29,30 \
    --name_body_to_trace seg27 \
    --anatomy_volume_name spine_seg \
    --csv_filename_static_traces /home/bigss/bigss/catkin_ws/src/continuum-manip-volumetric-drilling-plugin/resources/axis.csv
