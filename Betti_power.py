# -*- coding: utf-8 -*-
"""
Created on Fri May 10 00:59:29 2024

Explore Power

@author: Yihan Liu
"""

import sys
import numpy as np
import subprocess
import bisect
import matplotlib.pyplot as plt
from scipy.signal import spectrogram
from matplotlib.lines import Line2D

def process_rotor_performance(input_file = "Cp_Ct.NREL5MW.txt"):
    """
    This function will read the power coefficient surface from a text file generated
    by AeroDyn v15 and store the power coefficient in a 2D list

    Parameters
    ----------
    input_file : String, optional
        The file name of the pwer coefficient

    Returns
    -------
    C_p : 2D list
        The power coefficient. col: pitch angle, row: TSR value
    C_t : 2D list
        The thrust coefficient. col: pitch angle, row: TSR value
    pitch_angles : list
        The pitch angle corresponding to the col of C_p
    TSR_values : list
        The TSR values corresponding to the row of C_p

    """
    
    pitch_angles = []
    TSR_values = []

    with open(input_file, 'r') as file:
        lines = file.readlines()

        # Extract pitch angle vector
        pitch_angles_line = lines[4]
        # Extract TSR value vector
        TSR_values_line = lines[6]
        
        pitch_angles = [float(num_str) for num_str in pitch_angles_line.split()]
        TSR_values = [float(num_str) for num_str in TSR_values_line.split()]
        
        C_p = []
        for i in range(12, 12 + len(TSR_values)):
            Cp_row = [float(num_str) for num_str in lines[i].split()]
            C_p.append(Cp_row)
            
        C_t = []
        for i in range(16 + len(TSR_values), 16 + len(TSR_values) + len(TSR_values)):
            Ct_row = [float(num_str) for num_str in lines[i].split()]
            C_t.append(Ct_row)

    return C_p, C_t, pitch_angles, TSR_values


def CpCtCq(TSR, beta, performance):
    """
    Find the power coefficient based on the given TSR value and pitch angle

    Parameters
    ----------
    TSR : Tip speed ratio
    beta : blade pitch angle
    performance: The rotor performance generated by processing process_rotor_performance()

    Returns
    -------
    C_p: float
        power coefficient
    C_t: float
        thrust coefficient
    """
    beta = np.rad2deg(beta)

    C_p = performance[0] 
    C_t = performance[1]
    pitch_list = performance[2] 
    TSR_list = performance[3]
    
    # Find the closed pitch and TSR value in the list
    pitch_index = bisect.bisect_left(pitch_list, beta)
    TSR_index = bisect.bisect_left(TSR_list, TSR)
    
    # Correct the index if it's out of bounds or if the previous value is closer
    if pitch_index != 0 and (pitch_index == len(pitch_list) or abs(beta - pitch_list[pitch_index - 1]) < abs(beta - pitch_list[pitch_index])):
        pitch_index -= 1
    if TSR_index != 0 and (TSR_index == len(TSR_list) or abs(TSR - TSR_list[TSR_index - 1]) < abs(TSR - TSR_list[TSR_index])):
        TSR_index -= 1
    
    # Get the C_p value at the index 
    return C_p[TSR_index][pitch_index], C_t[TSR_index][pitch_index]


def genWind(v_w, end_time, time_step, seed):
    """
    Use Turbsim to generate a wind with turbulence.

    Parameters
    ----------
    v_w : float
        the average wind speed
    end_time : float
        the time to analysis. Should be consistent with the model driver
    time_step : float
        the time step to analysis. Should be consistent with the model driver

    Returns
    -------
    horSpd : list
        A list of horizontal wind speed computed at each time step

    """
    end_time += 1
        
    # Generate seeds for random wind model
    #seed1 = np.random.randint(-2147483648, 2147483648)
    #seed2 = np.random.randint(-2147483648, 2147483648)
    #seed = [seed1, seed2]
    path_inp = 'TurbSim_2/TurbSim.inp'
    
    
    # Open the inp file and overwrite with given parameters
    with open(path_inp, 'r') as file:
        lines = file.readlines()
        
    # Overwrite with new seeds
    line = lines[4].split()
    line[0] = str(seed[0])
    lines[4] = ' '.join(line) + '\n'

    line = lines[5].split()
    line[0] = str(seed[1])
    lines[5] = ' '.join(line) + '\n'
    
    # Overwrite "AnalysisTime" and "UsableTime"
    line = lines[21].split()
    line[0] = str(end_time)
    lines[21] = ' '.join(line) + '\n'
    
    # Overwrite the "TimeStep "
    line = lines[20].split()
    line[0] = str(time_step)
    lines[20] = ' '.join(line) + '\n'
    
    # Overwrite the average reference wind velocity
    line = lines[39].split()
    line[0] = str(v_w)
    lines[39] = ' '.join(line) + '\n'
    
    # Update the input file
    with open(path_inp, 'w') as file:
        file.writelines(lines)
    
    # Run the Turbsim to generate wind
    path_exe = "TurbSim_2/bin/TurbSim_x64.exe"
    #os.system(path_exe + " " + path_inp)
    command = [path_exe, path_inp]
    subprocess.run(command)
    # Read the output file
    path_hh = 'TurbSim_2/TurbSim.hh'
    
    with open(path_hh, 'r') as file:
        lines = file.readlines()
    
    # Skip the header
    data = lines[8:]
    
    horSpd = []

    for line in data:
        columns = line.split()
        horSpd.append(float(columns[1]))  
    

    return np.array(horSpd)




def pierson_moskowitz_spectrum(U19_5, zeta, eta, t, random_phases):
    """
    This function generates the Pierson-Moskowitz spectrum for a given wind speed U10 and frequency f.
    
    parameters
    ----------
    U19_5 : float
        the average wind speed at 19.5m above the sea surface
    zeta : float
        the x component to evaluate
    eta : float
        the y component to evaluate. (Note: the coordinate system here is different
                                      from the Betti model. The downward is negative
                                      in this case)
    t: float
        the time to evaluate.
    random_phase : Numpy Array
        the random phase to generate wave. Should be in [0, 2*pi)

    Returns
    -------
    wave_eta : float
        The wave elevation
    [v_x, v_y, a_x, a_y]: list
        The wave velocity and acceleration in x and y direction
    """
    g = 9.81  # gravitational constant
    alpha = 0.0081  # Phillips' constant

    f_pm = 0.14*(g/U19_5)  # peak frequency
    
    N = 400
    
    cutof_f = 3*f_pm # Cutoff frequency
    
    f = np.linspace(0.1, cutof_f, N) # Array
    omega = 2*np.pi*f # Array
    delta_f = f[1] - f[0] # Array

    S_pm = (alpha*g**2/((2*np.pi)**4*f**5))*np.exp(-(5/4)*(f_pm/f)**4) # Array
    
    a = np.sqrt(2*S_pm*delta_f)
    k = omega**2/g    
    
    # Generate random phases all at once
    
    
    # Perform the calculations in a vectorized manner
    sin_component = np.sin(omega*t - k*zeta + random_phases)
    cos_component = np.cos(omega*t - k*zeta + random_phases)
    exp_component = np.exp(k*eta)
    
    wave_eta = np.sum(a * sin_component)
    
    v_x = np.sum(omega * a * exp_component * sin_component)
    v_y = np.sum(omega * a * exp_component * cos_component)
    
    a_x = np.sum((omega**2) * a * exp_component * cos_component)
    a_y = -np.sum((omega**2) * a * exp_component * sin_component)

    return wave_eta, [v_x, v_y, a_x, a_y]



def structure(x_1, beta, omega_R, t, Cp_type, performance, v_w, v_aveg, random_phases):
    """
    The structure of the Betti model

    Parameters
    ----------
    x_1 : np.array
        The state vector: [zeta v_zeta eta v_eta alpha omega]^T
    beta : float
        The blade pitch angle
    omega_R : double
        Rotor speed
    t : float
        Time
    Cp_type : int
        The mode to compute the power and thrust coefficient. 
        (0: read file; 1: use AeroDyn v15)
    performance: list
        Used when Cp_type = 0. The rotor performance parameter pass to CpCtCq(TSR, beta, performance)
    v_w: float
        The wind speed with turbulent
    v_aveg: float
        The average wind speed used to compute wave
    random_phase: Numpy Array
        The random parameter used to compute wave

    Returns
    -------
    np.linalg.inv(E) @ F: Numpy Array
        The derivative for the state vector
    v_in : float
        The relative wind speed
    Cp : float
        The power coefficient

    """
    
    zeta = x_1[0] # surge (x) position
    v_zeta = x_1[1] # surge velocity
    eta = x_1[2] # heave (y) position
    v_eta = x_1[3] # heave velocity
    alpha = x_1[4] # pitch position
    omega = x_1[5] # pitch velocity    
    
    g = 9.80665  # (m/s^2) gravity acceleration
    rho_w = 1025  # (kg/m^3) water density

    # Coefficient matrix E
    # Constants and parameters
    M_N = 240000  # (kg) Mass of nacelle
    M_P = 110000  # (kg) Mass of blades and hub
    M_S = 8947870  # (kg) Mass of "structure" (tower and floater)
    m_x = 11127000  # (kg) Added mass in horizontal direction
    m_y = 1504400  # (kg) Added mass in vertical direction

    d_Nh = -1.8  # (m) Horizontal distance between BS and BN
    d_Nv = 126.9003  # (m) Vertical distance between BS and BN
    d_Ph = 5.4305  # (m) Horizontal distance between BS and BP
    d_Pv = 127.5879  # (m) Vertical distance between BS and BP

    J_S = 3.4917*10**9 # (kg*m^2) "Structure" moment of inertia
    J_N = 2607890  # (kg*m^2) Nacelle moment of inertia
    J_P = 50365000  # (kg*m^2) Blades, hub and low speed shaft moment of inertia

    M_X = M_S + m_x + M_N + M_P
    M_Y = M_S + m_y + M_N + M_P
    
    d_N = np.sqrt(d_Nh**2 + d_Nv**2)
    d_P = np.sqrt(d_Ph**2 + d_Pv**2)

    M_d = M_N*d_N + M_P*d_P
    J_TOT = J_S + J_N + J_P + M_N*d_N**2 + M_P*d_P**2

    E = np.array([[1, 0, 0, 0, 0, 0],
         [0, M_X, 0, 0, 0, M_d*np.cos(alpha)],
         [0, 0, 1, 0, 0, 0],
         [0, 0, 0, M_Y, 0, M_d*np.sin(alpha)],
         [0, 0, 0, 0, 1, 0],
         [0, M_d*np.cos(alpha), 0, M_d*np.sin(alpha), 0, J_TOT]]) 

    #####################################################################
    # Force vector F
    
    h = 200  # (m) Depth of water
    h_pt = 47.89  # (m) Height of the floating structure
    r_g = 9  # (m) Radius of floater
    d_Sbott = 10.3397  # (m) Vertical distance between BS and floater bottom
    r_tb = 3  # (m) Maximum radius of the tower
    d_t = 10.3397  # (m) Vertical distance between BS and hooks of tie rods
    l_a = 27  # (m) Distance between the hooks of tie rods
    l_0 = 151.73  # (m) Rest length of tie rods
    
    K_T1 = 2*(1.5/l_0)*10**9  # (N/m) Spring constant of lateral tie rods
    K_T2 = 2*(1.5/l_0)*10**9  # (N/m) Spring constant of lateral tie rods
    K_T3 = 4*(1.5/l_0)*10**9  # (N/m) Spring constant of central tie rod

    d_T = 75.7843 # (m) Vertical distance between BS and BT
    rho = 1.225 # (kg/m^3) Density of air
    C_dN = 1 # (-) Nacelle drag coefficient
    A_N = 9.62 # (m^2) Nacelle area
    C_dT = 1 # (-) tower drag coefficient
    '''
    H_delta = np.array([[-2613.44, 810.13],
                        [810.13, 1744.28]]) # (-) Coefficient for computing deltaFA
    F_delta = np.array([-22790.37, -279533.43]) # (-) Coefficient for computing deltaFA
    C_delta = 10207305.54 # (-) Coefficient for computing deltaFA
    '''
    A = 12469 # (m^2) Rotor area
    n_dg= 2 # （-） Number of floater sub-cylinders
    C_dgper = 1 # (-) Perpendicular cylinder drag coefficient
    C_dgpar = 0.006 # (-) Parallel cylinder drag coefficient
    C_dgb = 1.9 # (-) Floater bottom drag coefficient
    R = 63 # (m) Radius of rotor
    den_l = 116.027 # (kg/m) the mass density of the mooring lines
    dia_l = 0.127 # (m) the diameter of the mooring lines
    h_T = 87.6 # (m) the height of the tower
    D_T = 4.935 # (m) the main diameter of the tower

    # Weight Forces
    Qwe_zeta = 0
    Qwe_eta = (M_N + M_P + M_S)*g
    Qwe_alpha = ((M_N*d_Nv + M_P*d_Pv)*np.sin(alpha) + (M_N*d_Nh + M_P*d_Ph )*np.cos(alpha))*g

    # Buoyancy Forces
    h_wave = pierson_moskowitz_spectrum(v_aveg, zeta, 0, t, random_phases)[0] + h
    h_p_rg = pierson_moskowitz_spectrum(v_aveg, zeta + r_g, 0, t, random_phases)[0] + h
    h_n_rg = pierson_moskowitz_spectrum(v_aveg, zeta - r_g, 0, t, random_phases)[0] + h
    
    h_w = (h_wave + h_p_rg + h_n_rg)/3
    h_sub = min(h_w - h + eta + d_Sbott, h_pt)
    
    d_G = eta - h_sub/2
    V_g = h_sub*np.pi*r_g**2 + max((h_w - h + eta + d_Sbott) - h_pt, 0)*np.pi*r_tb**2

    Qb_zeta = 0
    Qb_eta = -rho_w*V_g*g
    Qb_alpha = -rho_w*V_g*g*d_G*np.sin(alpha)
    
    # Tie Rod Force
    
    D_x = l_a

    l_1 = np.sqrt((h - eta - l_a*np.sin(alpha) - d_t*np.cos(alpha))**2 
                  + (D_x - zeta - l_a*np.cos(alpha) + d_t*np.sin(alpha))**2)
    l_2 = np.sqrt((h - eta + l_a*np.sin(alpha) - d_t*np.cos(alpha))**2 
                  + (D_x + zeta - l_a*np.cos(alpha) - d_t*np.sin(alpha))**2)
    l_3 = np.sqrt((h - eta - d_t*np.cos(alpha))**2 + (zeta - d_t*np.sin(alpha))**2)

    f_1 = max(0, K_T1*(l_1 - l_0))
    f_2 = max(0, K_T2*(l_2 - l_0))
    f_3 = max(0, K_T3*(l_3 - l_0))

    theta_1 = np.arctan((D_x - zeta - l_a*np.cos(alpha) + d_t*np.sin(alpha))
                        /(h - eta - l_a*np.sin(alpha) - d_t*np.cos(alpha)))
    theta_2 = np.arctan((D_x + zeta - l_a*np.cos(alpha) - d_t*np.sin(alpha))
                        /(h - eta + l_a*np.sin(alpha) - d_t*np.cos(alpha)))
    theta_3 = np.arctan((zeta - d_t*np.sin(alpha))/(h - eta - d_t*np.cos(alpha)))

    v_tir = (0.5*dia_l)**2*np.pi
    w_tir = den_l*g
    b_tir = rho_w*g*v_tir
    lambda_tir = w_tir - b_tir

    Qt_zeta = f_1*np.sin(theta_1) - f_2*np.sin(theta_2) - f_3*np.sin(theta_3)
    Qt_eta = f_1*np.cos(theta_1) + f_2*np.cos(theta_2) + f_3*np.cos(theta_3) + 4*lambda_tir*l_0
    Qt_alpha = (f_1*(l_a*np.cos(theta_1 + alpha) - d_t*np.sin(theta_1 + alpha)) 
                - f_2*(l_a*np.cos(theta_2 - alpha) - d_t*np.sin(theta_2 - alpha)) 
                + f_3*d_t*np.sin(theta_3 - alpha) + lambda_tir*l_0
                *(l_a*np.cos(alpha) - d_t*np.sin(alpha)) 
                - lambda_tir*l_0*(l_a*np.cos(alpha) 
                + d_t*np.sin(alpha)) - 2*lambda_tir*l_0*d_t*np.sin(alpha))

    # Wind Force
    v_in = v_w + v_zeta + d_P*omega*np.cos(alpha)

    TSR = (omega_R*R)/v_in

    Cp = 0
    Ct = 0
    
    Cp = CpCtCq(TSR, beta, performance)[0]
    Ct = CpCtCq(TSR, beta, performance)[1]

    
    FA = 0.5*rho*A*Ct*v_in**2
    FAN = 0.5*rho*C_dN*A_N*np.cos(alpha)*(v_w + v_zeta + d_N*omega*np.cos(alpha))**2
    FAT = 0.5*rho*C_dT*h_T*D_T*np.cos(alpha)*(v_w + v_zeta + d_T*omega*np.cos(alpha))**2
    
    Qwi_zeta = -(FA + FAN + FAT)
    Qwi_eta = 0
    Qwi_alpha = (-FA*(d_Pv*np.cos(alpha) - d_Ph*np.sin(alpha))
                 -FAN*(d_Nv*np.cos(alpha) - d_Nh*np.sin(alpha))
                 -FAT*d_T*np.cos(alpha))
    
    # Wave and Drag Forces
    h_pg = np.zeros(n_dg)
    v_per = np.zeros(n_dg) # v_perpendicular relative velocity between water and immersed body
    v_par = np.zeros(n_dg) # v_parallel relative velocity between water and immersed body
    a_per = np.zeros(n_dg) # a_perpendicular acceleration of water
    tempQh_zeta = np.zeros(n_dg)
    tempQh_eta = np.zeros(n_dg)
    tempQwa_zeta = np.zeros(n_dg)
    tempQwa_eta = np.zeros(n_dg)
    Qh_zeta = 0
    Qh_eta = 0
    Qwa_zeta = 0
    Qwa_eta = 0
    Qh_alpha = 0
    Qwa_alpha = 0
    
    v_x = [0, 0]
    v_y = [0, 0]
    a_x = [0, 0]
    a_y = [0, 0]
    height = [0, 0]
    
    for i in range(n_dg):

        h_pg[i] = (i + 1 - 0.5)*h_sub/n_dg
        height[i] = -(h_sub - h_pg[i])
        
        wave = pierson_moskowitz_spectrum(v_aveg, zeta, height[i], t, random_phases)[1]
        
        v_x[i] = wave[0]
        v_y[i] = wave[1]
        a_x[i] = wave[2]
        a_y[i] = wave[3]
        
        v_per[i] =  ((v_zeta + (h_pg[i] - d_Sbott)*omega*np.cos(alpha) - v_x[i])*np.cos(alpha)
                     + (v_eta + (h_pg[i] - d_Sbott)*omega*np.sin(alpha) - v_y[i])*np.sin(alpha))
        v_par[i] =  ((v_zeta + (h_pg[i] - d_Sbott)*omega*np.cos(alpha) - v_x[i])*np.sin(-alpha)
                    + (v_eta + (h_pg[i] - d_Sbott)*omega*np.sin(alpha) - v_y[i])*np.cos(alpha))
        a_per[i] = a_x[i]*np.cos(alpha) + a_y[i]*np.sin(alpha)
        
        tempQh_zeta[i] = (-0.5*C_dgper*rho_w*2*r_g*(h_sub/n_dg)*  np.abs(v_per[i])*v_per[i]*np.cos(alpha)
                        - 0.5*C_dgpar*rho_w*np.pi*2*r_g*(h_sub/n_dg)*  np.abs(v_par[i])*v_par[i]*np.sin(alpha))
        tempQh_eta[i] = (-0.5*C_dgper*rho_w*2*r_g*(h_sub/n_dg)* np.abs(v_per[i])*v_per[i]*np.sin(alpha)
                         - 0.5*C_dgpar*rho_w*np.pi*2*r_g*(h_sub/n_dg)* np.abs(v_par[i])*v_par[i]*np.cos(alpha))
        tempQwa_zeta[i] = (rho_w*V_g + m_x)*a_per[i]*np.cos(alpha)/n_dg
        tempQwa_eta[i] =  (rho_w*V_g + m_x)*a_per[i]*np.sin(alpha)/n_dg
        
        Qh_zeta += tempQh_zeta[i] 
        Qh_eta += tempQh_eta[i] 
        Qwa_zeta += tempQwa_zeta[i]
        Qwa_eta += tempQwa_eta[i]
        Qh_alpha += (tempQh_zeta[i]*(h_pg[i] - d_Sbott)*np.cos(alpha)
                    + tempQh_eta[i]*(h_pg[i] - d_Sbott)*np.sin(alpha))
        Qwa_alpha += (tempQwa_zeta[i]*(h_pg[i] - d_Sbott)*np.cos(alpha)
                    + tempQwa_eta[i]*(h_pg[i] - d_Sbott)*np.sin(alpha))
    
    Qh_zeta -= 0.5*C_dgb*rho_w*np.pi*r_g**2*np.abs(v_par[0])*v_par[0]*np.sin(alpha)
    Qh_eta -= 0.5*C_dgb*rho_w*np.pi*r_g**2*np.abs(v_par[0])*v_par[0]*np.cos(alpha)

    # net force in x DOF
    Q_zeta = Qwe_zeta + Qb_zeta + Qt_zeta + Qh_zeta + Qwa_zeta + Qwi_zeta + Qh_zeta# 
    # net force in y DOF
    Q_eta = Qwe_eta + Qb_eta + Qt_eta + Qh_eta + Qwa_eta + Qwi_eta + Qh_eta
    # net torque in pitch DOF
    Q_alpha = Qwe_alpha + Qb_alpha + Qt_alpha + Qh_alpha + Qwa_alpha + Qh_alpha + Qwi_alpha

    F = np.array([v_zeta, 
                  Q_zeta + M_d*omega**2*np.sin(alpha), 
                  v_eta, 
                  Q_eta - M_d*omega**2*np.cos(alpha), 
                  omega, 
                  Q_alpha])
    

    return np.linalg.inv(E) @ F, v_in, Cp, h_wave



def WindTurbine(omega_R, v_in, beta, T_E, t, Cp):
    """
    The drivetrain model 

    Parameters
    ----------
    omega_R : float
        The rotor speed
    v_in : float
        The relative wind speed
    beta : float
        The blade pitch angle
    T_E : float
        The generator torque
    t : float
        Time
    Cp : float
        The power coefficient

    Returns
    -------
    domega_R: float
        The derivative of rotor speed

    """
    
    # Constants and parameters
    J_G = 534.116 # (kg*m^2) Total inertia of electric generator and high speed shaft
    J_R = 35444067 # (kg*m^2) Total inertia of blades, hub and low speed shaft
    rho = 1.225 # (kg/m^3) Density of air
    A = 12469 # (m^2) Rotor area
    eta_G = 97 # (-) Speed ratio between high and low speed shafts
    
    tildeJ_R = eta_G**2*J_G + J_R
    tildeT_E = eta_G*T_E
    
    P_wind = 0.5*rho*A*v_in**3

    P_A = P_wind*Cp

    T_A = P_A/omega_R
    domega_R = (1/tildeJ_R)*(T_A - tildeT_E)

    return domega_R, P_A


def WindTurbine_fixed(omega_R_fixed, v_w, beta, T_E, t, performance):
    """
    The drivetrain model for fixed turbine

    Parameters
    ----------
    omega_R : float
        The rotor speed
    v_in : float
        The relative wind speed
    beta : float
        The blade pitch angle
    T_E : float
        The generator torque
    t : float
        Time
    Cp : float
        The power coefficient

    Returns
    -------
    domega_R: float
        The derivative of rotor speed

    """
    R = 63 # (m) Radius of rotor
    TSR = (omega_R_fixed*R)/v_w
    
    Cp = CpCtCq(TSR, beta, performance)[0]
    # Constants and parameters
    J_G = 534.116 # (kg*m^2) Total inertia of electric generator and high speed shaft
    J_R = 35444067 # (kg*m^2) Total inertia of blades, hub and low speed shaft
    rho = 1.225 # (kg/m^3) Density of air
    A = 12469 # (m^2) Rotor area
    eta_G = 97 # (-) Speed ratio between high and low speed shafts
    
    tildeJ_R = eta_G**2*J_G + J_R
    tildeT_E = eta_G*T_E
    
    P_wind = 0.5*rho*A*v_w**3

    P_A = P_wind*Cp

    T_A = P_A/omega_R_fixed
    domega_R_fixed = (1/tildeJ_R)*(T_A - tildeT_E)

    return domega_R_fixed, P_A
    

def Betti(x, t, beta, T_E, Cp_type, performance, v_w, v_aveg, random_phases):
    """
    Combine the WindTurbine model and structure model
    
    Parameters
    ----------
    x : np.array
        the state vector: [zeta, v_zeta, eta, v_eta, alpha, omega, omega_R]^T
    t : float
        time
    beta : float
        blade pitch angle
    T_E : float
        generator torque
    Cp_type : int
        The mode to compute the power and thrust coefficient. 
        (0: read file; 1: use AeroDyn v15)
    performance: list
        Used when Cp_type = 0. The rotor performance parameter pass to CpCtCq(TSR, beta, performance)
    v_w: float
        The wind speed with turbulent
    v_aveg: float
        The average wind speed used to compute wave
    random_phase: Numpy Array
        The random parameter used to compute wave

    Returns
    -------
    dxdt : Numpy Array
        The derivative of the state vector

    """
    x1 = x[:6]
    omega_R = x[6]
    omega_R_fixed = x[7]
    
    dx1dt, v_in, Cp, h_wave = structure(x1, beta, omega_R, t, Cp_type, performance, v_w, v_aveg, random_phases)
    dx2dt, P_A = WindTurbine(omega_R, v_in, beta, T_E, t, Cp)
    dx2dt_fixed, P_A_fixed = WindTurbine_fixed(omega_R_fixed, v_w, beta, T_E, t, performance)
    dxdt = np.append(np.append(dx1dt, dx2dt), dx2dt_fixed)
    
    return dxdt, h_wave, P_A, P_A_fixed


def rk4(Betti, x0, t0, tf, dt, beta_0, T_E, Cp_type, performance, v_w, v_wind, seed_wave):
    """
    Solve the system of ODEs dx/dt = Betti(x, t) using the fourth-order Runge-Kutta method.

    Parameters:
    Betti : function
        The function to be integrated.
    x0 : np.array
        Initial conditions.
    t0 : float
        Initial time.
    tf : float
        Final time.
    dt : float
        Time step.
    beta : float
        blade pitch angle
    T_E : float
        generator torque
    Cp_type : int
        The mode to compute the power and thrust coefficient. 
        (0: read file; 1: use AeroDyn v15)
    performance: list
        Used when Cp_type = 0. The rotor performance parameter pass to CpCtCq(TSR, beta, performance)
    v_w: float
        The average wind speed
    wind: wind_mutiprocessing
        Used to for simulaton mutiprocessing. Its field containing the wind speed turbulent
        for all simulations
    
    Returns:
    t, x, v_wind[:len(t)], wave_eta
    np.array, np.array, np.array, np.raay
        Time points and corresponding values of state, wind velocities, sea surface elevation
        Each row is a state vector 
    """
    
    d_BS = 37.550 # (m) The position of center of weight of BS (platform and tower)
    
    n = int((tf - t0) / dt) + 1
    t = np.linspace(t0, tf, n)
    x = np.empty((n, len(x0)))
    x[0] = x0

    
    # generate a random seed
    state_before = np.random.get_state()
    #wave_seed = np.random.randint(0, high=10**7)
    np.random.seed(seed_wave)
    random_phases = 2*np.pi*np.random.rand(400)
    np.random.set_state(state_before)
    ###########################################################################
    # PI controller
    integral = 0
    beta = beta_0
    
    def PI_blade_pitch_controller(omega_R, dt, beta, integral, error, i):

        
        eta_G = 97 # (-) Speed ratio between high and low speed shafts
        J_G = 534.116 # (kg*m^2) Total inertia of electric generator and high speed shaft
        J_R = 35444067 # (kg*m^2) Total inertia of blades, hub and low speed shaft
        tildeJ_R = eta_G**2*J_G + J_R
    
        rated_omega_R = 1.26711 # The rated rotor speed is 12.1 rpm
        #rated_omega_R = 1.571
        zeta_phi = 0.7
        omega_phin = 0.6
        beta_k = 0.1099965
        dpdbeta_0 = -25.52*10**6
        
        GK = 1/(1+(beta/beta_k))
        
        K_p = 0.0765*(2*tildeJ_R*rated_omega_R*zeta_phi*omega_phin*GK)/(eta_G*(-dpdbeta_0))
        K_i = 0.013*(tildeJ_R*rated_omega_R*omega_phin**2*GK)/(eta_G*(-dpdbeta_0))
        K_d = 0.187437
        
        error_omega_R = omega_R - rated_omega_R
        error[i] = error_omega_R

        P = K_p*eta_G*error_omega_R
        integral = integral + dt*K_i*eta_G*error_omega_R
        D = (K_d*(error[i] - error[i-1]))/dt

        delta_beta = P + integral + D
        
        # set max change rate in 8 degree per second
        
        if delta_beta > 0 and delta_beta/dt > 0.139626:
            delta_beta = 0.139626*dt
        elif delta_beta < 0 and delta_beta/dt < -0.139626:
            delta_beta = -0.139626*dt
        
        beta += delta_beta
        
        if beta <= 0:
            beta = 0
        elif beta >= np.pi/4:
            beta = np.pi/4
        
        return beta, integral, error

    ###########################################################################

    error = np.empty(n)
    betas = []
    h_waves = []
    P_A = []
    P_fix = []
    for i in range(n - 1):
        #betas.append(beta)
        k1, h_wave, power, power_fixed = Betti(x[i], t[i], beta, T_E, Cp_type, performance, v_wind[i], v_w, random_phases)
        k2 = Betti(x[i] + 0.5 * dt * k1, t[i] + 0.5 * dt, beta, T_E, Cp_type, performance, v_wind[i], v_w, random_phases)[0]
        k3 = Betti(x[i] + 0.5 * dt * k2, t[i] + 0.5 * dt, beta, T_E, Cp_type, performance, v_wind[i], v_w, random_phases)[0]
        k4 = Betti(x[i] + dt * k3, t[i] + dt, beta, T_E, Cp_type, performance, v_wind[i], v_w, random_phases)[0]
        x[i + 1] = x[i] + dt * (k1 + 2*k2 + 2*k3 + k4) / 6

        #beta, integral, error = PI_blade_pitch_controller(x[i][6], dt, beta, integral, error, i)
        
        h_waves.append(h_wave)
        P_A.append(power)
        P_fix.append(power_fixed)
        
    
    x[:, 4] = -np.rad2deg(x[:, 4])
    x[:, 5] = -np.rad2deg(x[:, 5])
    x[:, 6] = (60 / (2*np.pi))*x[:, 6]
    x[:, 7] = (60 / (2*np.pi))*x[:, 7]
   
    x[:, 0:4] = -x[:, 0:4]
    x[:, 2] += d_BS


    # Output wave elevation at zeta = 0
    wave_eta = []
    for i in t:
        wave_eta.append(pierson_moskowitz_spectrum(v_w, -2.61426271, 0, i, random_phases)[0])
        
    steps = int(0.5 / dt)
    # dicard data for first 500s
    discard_steps = int(500 / 0.5) 

    t_sub = t[::steps][discard_steps:]
    x_sub = x[::steps][discard_steps:]
    v_wind_sub = v_wind[:len(t)][::steps][discard_steps:]
    wave_eta_sub = np.array(wave_eta)[::steps][discard_steps:]
    h_wave_sub = np.array(h_waves)[::steps][discard_steps:]
    betas_sub = betas[::steps][discard_steps:]
    P_A_sub = P_A[::steps][discard_steps:]
    P_fix_sub = P_fix[::steps][discard_steps:]
    P_A_sub.append(P_A_sub[-1])
    P_fix_sub.append(P_fix_sub[-1])

    
    return t_sub-t_sub[0], x_sub, v_wind_sub, wave_eta_sub, h_wave_sub, betas_sub, P_A_sub, P_fix_sub


def main(end_time, v_w, x0, seeds, seed_wave, time_step = 0.05, Cp_type = 0):
    """
    Cp computation method

    Parameters
    ----------
    Cp_type : TYPE, optional
        DESCRIPTION. The default is 0.
        0: read the power coefficient file. Fast but not very accurate
        1: run the AeroDyn 15 driver, very accurate and very slow

    Returns
    -------
    t: np.array
        The time array
    x: 2D array:
        The state at each time.The row of x corresponding to each time step.
        The column is each state [surge, surge_velocity, heave, heave_velocity, pitch, pitch_rate, rotor_speed]
    v_wind: list
        The wind speed at each time step
    wave_eta: list
        The wave elevation at surge = 0 for each time step
    """
    performance = process_rotor_performance()
    
    start_time = 0
    
    # modify this to change initial condition
    #[zeta, v_zeta, eta, v_eta, alpha, omega, omega_R]
    #v_wind = genWind(v_w, end_time, time_step, seeds)
    #v_wind = np.load(f'reproduced_results/turbsim_output/{seeds[0]}_{seeds[1]}.npy')
    #v_wind = genWind_seeds(seeds)
    v_wind = np.full(45000, v_w)

    # modify this to change run time and step size
    #[Betti, x0 (initial condition), start time, end time, time step, beta, T_E]

    t, x, v_wind, wave_eta, h_wave, betas, P_A_sub, P_fix_sub = rk4(Betti, x0, start_time, end_time, time_step, np.deg2rad(3.83), 43093.55, Cp_type, performance, v_w, v_wind, seed_wave)

    # return the output to be ploted
    return t, x, v_wind, wave_eta, h_wave, betas, P_A_sub, P_fix_sub


    
def reproduce_save_driver(seeds, simulation_time, v_w):

    end_time = simulation_time + 500 #end_time < 3000
    
    seeds_wind = [seeds[0], seeds[1]]
    seed_wave = seeds[2]
    
    
    x0 = np.array([-2.61426271, 
                     -0.00299848190, 
                     37.5499264, 
                     -0.0558194064,
                     0.00147344971, 
                     -0.000391112846, 
                     1.26855822,
                     1.26855822])
    t, x, v_wind, wave_eta, h_wave, betas, P_A, P_fix_sub = main(end_time, v_w, x0, seeds_wind, seed_wave)
    end_time -= 500
    
    np.savez(f'{seeds[0]}_{seeds[1]}_{seeds[2]}.npz', 
                                                    t=t,  
                                                    x=x, 
                                                    v_wind=v_wind, 
                                                    wave_eta=wave_eta, 
                                                    betas=betas,
                                                    h_wave=h_wave,
                                                    P_A=P_A)
    
    return t, x, wave_eta, P_A, P_fix_sub

#####################################################################################
#####################################################################################

def load_data(seeds):
    '''
    load the simulation results data
    load the pitch acceleration
    load the percentile and extreme value
    '''
    
    output_file_name = f'{seeds[0]}_{seeds[1]}_{seeds[2]}.npz'

    data = np.load(f'reproduced_results/data/{output_file_name}', allow_pickle=True)
    
    # Extracting the data
    t = data['t'][:-1]
    state = data['x'][:-1]
    #beta = np.rad2deg(data['betas'])
    x = data['x'][:-1]
    wind_speed = data['v_wind'][:-1]
    wave_eta = data['wave_eta'][:-1]
    data.close()
    
    pitch_rate = x[:, 5]  
    pitch_acceleration = np.diff(pitch_rate)
    last_acceleration = pitch_acceleration[-1][None]
    pitch_acceleration = np.concatenate((pitch_acceleration, last_acceleration), axis=0)[:, None] 
    state = np.concatenate((x[:, :6], pitch_acceleration), axis=1)
    
                        
                           
    # Extracting percentile data
    percentile_file_path = 'reproduced_results/percentile_extreme.npz'
    data = np.load(percentile_file_path)

    percentile_87_5 = data['percentile_87_5'][:-1]
    percentile_12_5 = data['percentile_12_5'][:-1]

    percentile_62_5 = data['percentile_62_5'][:-1]
    percentile_37_5 = data['percentile_37_5'][:-1]

    percentile_50 = data['percentile_50'][:-1]

    max_state = data['max_state'][:-1]
    min_state = data['min_state'][:-1]
    data.close()
    figure_directory = 'reproduced_results/figure'
    
    ######################################################################
    state_names = ['Surge (m)', 'Surge Velocity (m/s)', 'Heave (m)', 'Heave Velocity (m/s)', 
                   'Pitch Angle (deg)', 'Pitch Rate (deg/s)', 'Pitch Acceleration (deg/s^2)', 'Rotor Speed (rpm)']


    
    data.close()


    
    def plot_helper(ax):
        
        # plot wind
        ax[0].plot(t, wind_speed, color='black', linewidth=0.5)
        ax[0].set_xlabel('Time (s)', fontsize=12)
        ax[0].set_title('Wind Speed (m/s)', fontsize=15)
        #ax[0].set_ylabel('Wind speed (m/s)')
        ax[0].tick_params(axis='both', labelsize=16) 
        ax[0].grid(True)
        ax[0].set_xlim(0, t[-1])
        
        # plot wave
        ax[1].plot(t, wave_eta, color='black', linewidth=0.5)
        ax[1].set_xlabel('Time (s)', fontsize=12)
        ax[1].set_title('Wave Elevation', fontsize=15)
        #ax[1].set_ylabel('Wave height (m)')
        ax[1].tick_params(axis='both', labelsize=16) 
        ax[1].grid(True)
        ax[1].set_xlim(0, t[-1])
        
        # plot 7 states
        for j in range(7):
        #for j in range(6):
            ax[j+2].plot(t, max_state[:,j], alpha=0.6, color='green', linewidth=0.5)
            ax[j+2].plot(t, min_state[:,j], alpha=0.6, color='orange', linewidth=0.5)

            ax[j+2].plot(t, state[:, j], color='black', linewidth=0.5)
            ax[j+2].set_xlabel('Time (s)', fontsize=12)
            #ax[j+2].set_ylabel(f'{state_names[j]}')
            
            ax[j+2].fill_between(t, percentile_12_5[:, j], percentile_87_5[:, j], color='b', alpha=0.3, edgecolor='none')
            ax[j+2].fill_between(t, percentile_37_5[:, j], percentile_62_5[:, j], color='b', alpha=0.3, edgecolor='none')
            ax[j+2].plot(t, percentile_50[:, j], color='r', alpha=0.9, linewidth=0.5)
            
            ax[j+2].set_title(state_names[j], fontsize=15)
            ax[j+2].grid(True)
            ax[j+2].set_xlim(0, t[-1])
            
            ax[j+2].tick_params(axis='both', labelsize=16) 
        
        '''
        ax[8].plot(t, state[:, -1], color='black', linewidth=0.5)
        ax[8].set_xlabel('Time (s)', fontsize=12)
        #ax[j+2].set_ylabel(f'{state_names[j]}')
        
       
        ax[8].set_title("Rotor Speed (rpm)", fontsize=15)
        ax[8].grid(True)
        ax[8].set_xlim(0, t[-1])
        
        ax[8].tick_params(axis='both', labelsize=16) 
        
        ax[9].plot(t, beta, color='black', linewidth=0.5)
        ax[9].set_xlabel('Time (s)', fontsize=12)
        #ax[j+2].set_ylabel(f'{state_names[j]}')
        
       
        ax[9].set_title("Blade Pitch Angle (deg)", fontsize=15)
        ax[9].grid(True)
        ax[9].set_xlim(0, t[-1])
        
        ax[9].tick_params(axis='both', labelsize=16) 
        '''
        ax[9].axis('off')
        
        legend_elements = [Line2D([0], [0], color='black', lw=1, alpha=1, label='One Trajectory'),
                           Line2D([0], [0], color='r', lw=1, alpha=0.9, label='Median'),
                           Line2D([0], [0], color='b', lw=8, alpha=0.6, label='Central 25th Percentile'),
                           Line2D([0], [0], color='b', lw=8, alpha=0.3, label='Central 75th Percentile'),
                           Line2D([0], [0], color='green', lw=1, alpha=0.6, label='The Maximum at Each Time Step'),
                           Line2D([0], [0], color='orange', lw=1, alpha=0.6, label='The Minimum at Each Time Step')]
        
        ax[9].legend(handles=legend_elements, loc='center', fontsize=17.5)
      
    
    # for 8 states including pitch acceleration:

    # create subplots for each simulation index in max_occ_sim
    fig_max_occ, ax_max_occ = plt.subplots(5, 2, figsize=(12, 16))
    ax_max_occ = ax_max_occ.flatten()
    
    plot_helper(ax_max_occ)
    
    plt.tight_layout() 
    plt.savefig(f'./{figure_directory}/large_surge_1_rotor.png')
    plt.show()
    plt.close(fig_max_occ) 
        
    return np.std(state[:, 4])
        

seeds = [ -402337, -6699134,  7762480]




t, x, wave_eta, P_A, P_fix_sub = reproduce_save_driver(seeds, 300, 8)
omega = x[:,6]
omega_fix = x[:,7]

plt.figure(figsize=(12, 10))

# Plotting omega and omega_fixed vs. t
plt.subplot(3, 1, 1)
plt.plot(t, omega, label='Omega (ω)')
plt.plot(t, omega_fix, label='Fixed Omega (ω_fixed)', linestyle='--')
plt.title('Omega (ω) and Fixed Omega (ω_fixed) vs Time (t)')
plt.xlabel('Time (t)')
plt.ylabel('Omega (ω)')
plt.legend()  # Adding legend to the plot
plt.grid(True)

# Plotting wave_eta vs. t
plt.subplot(3, 1, 2)
plt.plot(t, wave_eta, label='Wave Height (wave_eta)', color='green')
plt.title('Wave Height (wave_eta) vs Time (t)')
plt.xlabel('Time (t)')
plt.ylabel('Wave Height (wave_eta)')
plt.legend()  # Adding legend to the plot
plt.grid(True)

# Plotting P_A and P_fixed_sub vs. t
plt.subplot(3, 1, 3)
plt.plot(t, P_A, label='Power (P_A)', color='red')
plt.plot(t, P_fix_sub, label='Fixed Power (P_fixed_sub)', color='blue', linestyle='--')
plt.title('Power (P_A) and Fixed Power (P_fixed_sub) vs Time (t)')
plt.xlabel('Time (t)')
plt.ylabel('Power')
plt.legend()  # Adding legend to the plot
plt.grid(True)

# Adjust layout and show plot
plt.tight_layout()
plt.show()