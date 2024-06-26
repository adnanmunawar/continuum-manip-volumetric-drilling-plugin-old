#!/usr/bin/env python3

import rospy

from geometry_msgs.msg import TransformStamped
from sensor_msgs.msg import JointState
from ambf_msgs.msg import RigidBodyState
import numpy as np
import matplotlib.pyplot as plt
import tf.transformations as tr
import time
import os

class free_space_calibration:


    def __init__(self, save_dir):
        self.save_dir = save_dir

        rospy.init_node('free_space_calibration', anonymous=True)
        base_marker_sub = rospy.Subscriber('ambf/env/snake_stick/State', RigidBodyState, self.ambf_base_marker_sub_callback)
        tip_marker_sub  = rospy.Subscriber('ambf/env/Burr/State', RigidBodyState, self.ambf_tip_marker_sub_callback)
        
        bend_sub = rospy.Subscriber('/ambf/volumetric_drilling/bend_motor/measured_js/', JointState, self.bend_sub_callback)
        self.bend_pub = rospy.Publisher('/ambf/volumetric_drilling/bend_motor/move_jp/', JointState)

        self.collect = False
        self.reset_sublists()

        self.simulation_units_to_meter = 0.1

        self.ms = 0.001
        self.sec = 1.0
        self.base_transform = TransformStamped()
        self.tip_transform = TransformStamped()
        self.base_zero_transform = np.eye(4)   
        self.tip_zero_transform = np.eye(4)

        self.base_transforms_measured_all = []
        self.tip_transforms_measured_all = []
        self.base_transforms_measured_avg = []
        self.tip_transforms_measured_avg = []
        self.bend_motor_pos_all = []
        self.bend_motor_cmd_all = []

    def run(self):
       do_run = True
       while do_run:

            user_in = input("Press Enter to collect datapoint, 'X' to exit, 'F' to fit: , 'Z' to set zero transform, 'A' to auto calibrate: ")
            
            # Exit
            if user_in == "X": break

            # Load previous data from file (allows appending new data or removing bad data outside and then reloading)
            if user_in == "L":
                self.load_from_output()
                continue

            # Automatically run data collection over range specified below
            if user_in == "A":
                reps = 1
                motor_max = 0.20
                motor_min = -motor_max
                motor_pos = np.linspace(motor_min,motor_max,101)

                motor_pos_rev = np.flipud(motor_pos)
                pos = np.append(motor_pos,motor_pos_rev)
                for r in range(reps):
                    for p in pos:
                        self.bend_motor_cmd_all.append(p)
                        msg_pub = JointState()
                        msg_pub.position = [p]
                        self.bend_pub.publish(msg_pub)
                        rospy.sleep(3000*self.ms)
                        self.collect_over_period(500*self.ms) 
                        self.save_to_output()
                continue
            
            # Fit calibration
            if user_in == "F":
                self.fit_calibration()
                continue

            self.collect_over_period(2000*self.ms) 
            
            if user_in == 'Z':
                self.base_zero_transform = self.base_transforms_measured_avg[-1]
                self.tip_zero_transform = self.tip_transforms_measured_avg[-1]
        
            self.save_to_output()        

    def collect_over_period(self, collect_duration):
        # Collect data
        self.reset_sublists()
        self.collect = True
        rospy.sleep(collect_duration)
        self.collect = False

        # Store data internally
        self.base_transforms_measured_all.append(self.base_transforms_sublist)
        self.tip_transforms_measured_all.append(self.tip_transforms_sublist)
        self.bend_motor_pos_all.append(self.bend_motor_pos_sublist)

        self.base_transforms_measured_avg.append(self.average_list_of_TransformStamped(self.base_transforms_sublist))
        self.tip_transforms_measured_avg.append(self.average_list_of_TransformStamped(self.tip_transforms_sublist))


    def average_list_of_TransformStamped(self,list_of_TS):
        N = len(list_of_TS)
        average = TransformStamped()
        average.transform.rotation.w = sum([T.transform.rotation.w for T in list_of_TS])/N
        average.transform.rotation.x = sum([T.transform.rotation.x for T in list_of_TS])/N
        average.transform.rotation.y = sum([T.transform.rotation.y for T in list_of_TS])/N
        average.transform.rotation.z = sum([T.transform.rotation.z for T in list_of_TS])/N
        average.transform.translation.x = sum([T.transform.translation.x for T in list_of_TS])/N
        average.transform.translation.y = sum([T.transform.translation.y for T in list_of_TS])/N
        average.transform.translation.z = sum([T.transform.translation.z for T in list_of_TS])/N

        R = average.transform.rotation
        p = average.transform.translation
        q = np.array([R.x,R.y,R.z,R.w])
        q = q / np.linalg.norm(q)
        g = tr.quaternion_matrix(q)
        g[0:3,-1] = np.array([p.x,p.y,p.z])
        return g

    def base_marker_sub_callback(self,transform):
        self.base_transform = transform
        if self.collect:
            self.base_transforms_sublist.append(transform)

    def tip_marker_sub_callback(self,transform):
        self.tip_transform = transform
        if self.collect:
            self.tip_transforms_sublist.append(transform)

    def ambf_base_marker_sub_callback(self,ambf_rigid_body_state):
        self.base_marker_sub_callback(ambf_rigid_body_state_to_transform_stamped(ambf_rigid_body_state, self.simulation_units_to_meter))
  
    def ambf_tip_marker_sub_callback(self,ambf_rigid_body_state):
        self.tip_marker_sub_callback(ambf_rigid_body_state_to_transform_stamped(ambf_rigid_body_state, self.simulation_units_to_meter))

    def bend_sub_callback(self,motor_pos):
        self.bend_motor_pos = motor_pos.position[0]
        if self.collect:
            self.bend_motor_pos_sublist.append(motor_pos.position[0])

    def reset_sublists(self):
        self.base_transforms_sublist = []
        self.tip_transforms_sublist = []
        self.bend_motor_pos_sublist = []

    def fit_calibration(self):
        lengths = self.bend_motor_cmd_all
        x = np.zeros(len(lengths))
        y = np.zeros(len(lengths))
        z = np.zeros(len(lengths))
        thz = np.zeros(len(lengths))

        print("bend lengths: ", lengths)
        base_T_tip_zero = np.linalg.inv(self.base_zero_transform) @ self.tip_zero_transform
        print("base_T_tip_zero: ", base_T_tip_zero) # Not using right now

        for i in range(len(lengths)):
            base_T_tip =  np.linalg.inv(self.base_transforms_measured_avg[i]) @ self.tip_transforms_measured_avg[i]
            x[i]=base_T_tip[0,3]
            y[i]=base_T_tip[1,3]
            z[i]=base_T_tip[2,3]
            print(base_T_tip)
            th,dir,_ = tr.rotation_from_matrix(base_T_tip)
            thz[i] = th * np.sign(dir[2])
            print(dir)

        l = np.array(lengths)
        degree = 3
        x_coeff = np.polyfit(l, x, degree)
        y_coeff = np.polyfit(l, y, degree)
        z_coeff = np.polyfit(l, z, degree)
        thz_coeff  = np.polyfit(l, thz, degree)

        poly_x = np.poly1d(x_coeff)
        poly_y = np.poly1d(y_coeff)
        poly_z = np.poly1d(z_coeff)
        poly_thz = np.poly1d(thz_coeff)

        new_l = np.linspace(min(l), max(l))
        new_x = poly_x(new_l)
        new_y = poly_y(new_l)
        new_z = poly_z(new_l)
        new_thz = poly_thz(new_l)

        fig, (ax_x, ax_y, ax_z, ax_thz) = plt.subplots(4)
        ax_x.plot(l, x, "o", new_l, new_x)
        ax_x.set(xlabel="cable length (mm)", ylabel="Tip X value (m)")
        ax_y.plot(l, y, "o", new_l, new_y)
        ax_y.set(xlabel="cable length (mm)", ylabel="Tip Y value (m)")
        ax_z.plot(l, z, "o", new_l, new_z)
        ax_z.set(xlabel="cable length (mm)", ylabel="Tip Z value (m)")
        ax_thz.plot(l, thz, "o", new_l, new_thz)
        ax_thz.set(xlabel="cable length (mm)", ylabel="Tip Rotation Angle (rad) (th_z)")  
        timestamp = time.strftime("%Y%m%d%H%M%S_")

        save_filename = self.save_dir+timestamp+"xyzthz_snake_polyfit_coeffs.txt"
        np.savetxt(save_filename,np.array((x_coeff,y_coeff,z_coeff,thz_coeff)))

        # additional estimates of dx,dy,dz as function of thz (essentially fitting terms of the jacobian to angle)
        poly_dx = poly_x.deriv()
        poly_dy = poly_y.deriv()
        poly_dz = poly_z.deriv()
        poly_dth = poly_thz.deriv()
        new_dx = poly_dx(new_l)
        new_dy = poly_dy(new_l)
        new_dz = poly_dz(new_l)
        new_dth = poly_dth(new_l)
        # find fit coefficients for dx,dy,dz as function of thz
        dx_thzcoeff = np.polyfit(new_thz, new_dx, degree)
        dy_thzcoeff = np.polyfit(new_thz, new_dy, degree)
        dz_thzcoeff = np.polyfit(new_thz, new_dz, degree)
        dth_thzcoeff = np.polyfit(new_thz, new_dth, degree)

        poly_dx_thz = np.poly1d(dx_thzcoeff)
        poly_dy_thz = np.poly1d(dy_thzcoeff)
        poly_dz_thz = np.poly1d(dz_thzcoeff)
        poly_dth_thz = np.poly1d(dth_thzcoeff)

        new_dx_thz = poly_dx_thz(new_thz)
        new_dy_thz = poly_dy_thz(new_thz)
        new_dz_thz = poly_dz_thz(new_thz)
        new_dth_thz = poly_dth_thz(new_thz)

        fig, (ax_dx, ax_dy, ax_dz, ax_dth) = plt.subplots(4)
        ax_dx.plot(new_thz, new_dx, "o", new_thz, new_dx_thz)
        ax_dx.set(xlabel="Tip Rotation Angle (rad) (th_z)", ylabel="Tip X value (m)")
        ax_dy.plot(new_thz, new_dy, "o", new_thz, new_dy_thz)
        ax_dy.set(xlabel="Tip Rotation Angle (rad) (th_z)", ylabel="Tip Y value (m)")
        ax_dz.plot(new_thz, new_dz, "o", new_thz, new_dz_thz)
        ax_dz.set(xlabel="Tip Rotation Angle (rad) (th_z)", ylabel="Tip Z value (m)")
        ax_dth.plot(new_thz, new_dth, "o", new_thz, new_dth_thz)
        ax_dth.set(xlabel="Tip Rotation Angle (rad) (th_z)", ylabel="Tip Rotation Angle (rad) (th_z)")

        save_filename = self.save_dir+timestamp+"dxdydzdthz_snake_polyfit_coeffs.txt"
        np.savetxt(save_filename,np.array((dx_thzcoeff,dy_thzcoeff,dz_thzcoeff,dth_thzcoeff)))

        print("Coefficients saved to " + save_filename)
        print("Close Graph to Continue:")
        plt.show()



    def save_to_output(self):
        np.save(self.save_dir+"base_transforms_measured_all.npy",np.array(self.base_transforms_measured_all))
        np.save(self.save_dir+"tip_transforms_measured_all.npy",np.array(self.tip_transforms_measured_all))
        np.save(self.save_dir+"base_transforms_measured_avg.npy",np.array(self.base_transforms_measured_avg))
        np.save(self.save_dir+"tip_transforms_measured_avg.npy",np.array(self.tip_transforms_measured_avg))
        np.save(self.save_dir+"base_zero_transform.npy",np.array(self.base_zero_transform))
        np.save(self.save_dir+"tip_zero_transform.npy",np.array(self.tip_zero_transform))
        np.save(self.save_dir+"bend_motor_pos_all.npy",np.array(self.bend_motor_pos_all))
        np.save(self.save_dir+"bend_motor_cmd_all.npy",np.array(self.bend_motor_cmd_all))

    def load_from_output(self):
        # ask user for directory to load from
        load_dir = input("Enter directory to load from: ")
        # check if directory exists
        if not os.path.exists(load_dir):
            print(f"Directory {load_dir} does not exist")
            return
        # check if directory ends with "/"
        if not load_dir.endswith("/"):
            load_dir += "/"
        self.base_transforms_measured_all = np.load(load_dir+"base_transforms_measured_all.npy", allow_pickle=True)
        self.tip_transforms_measured_all = np.load(load_dir+"tip_transforms_measured_all.npy", allow_pickle=True)
        self.base_transforms_measured_avg = np.load(load_dir+"base_transforms_measured_avg.npy", allow_pickle=True)
        self.tip_transforms_measured_avg = np.load(load_dir+"tip_transforms_measured_avg.npy", allow_pickle=True)
        self.base_zero_transform = np.load(load_dir+"base_zero_transform.npy", allow_pickle=True)
        self.tip_zero_transform = np.load(load_dir+"tip_zero_transform.npy", allow_pickle=True)
        self.bend_motor_pos_all = np.load(load_dir+"bend_motor_pos_all.npy", allow_pickle=True)
        self.bend_motor_cmd_all = np.load(load_dir+"bend_motor_cmd_all.npy", allow_pickle=True)
    

def ambf_rigid_body_state_to_transform_stamped(ambf_rigid_body_state, translation_scale=1.0):
    transform = TransformStamped()
    transform.transform.translation.x = ambf_rigid_body_state.pose.position.x * translation_scale
    transform.transform.translation.y = ambf_rigid_body_state.pose.position.y * translation_scale
    transform.transform.translation.z = ambf_rigid_body_state.pose.position.z * translation_scale
    transform.transform.rotation.x = ambf_rigid_body_state.pose.orientation.x
    transform.transform.rotation.y = ambf_rigid_body_state.pose.orientation.y
    transform.transform.rotation.z = ambf_rigid_body_state.pose.orientation.z
    transform.transform.rotation.w = ambf_rigid_body_state.pose.orientation.w
    return transform

if __name__ == '__main__':
    try:
        timestamp = time.strftime("%Y%m%d%H%M%S")
        calibration_save_directory = os.path.dirname(os.path.abspath(__file__))+"/output/"+timestamp+"/"
        # if not directory, then make it recursively
        if not os.path.exists(calibration_save_directory):
            os.makedirs(calibration_save_directory)
        cal_node = free_space_calibration(calibration_save_directory)
        cal_node.run()

    except rospy.ROSInterruptException:
        pass

