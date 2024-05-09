
import statsmodels.api as sm
import pandas as pd
import numpy as np
from sklearn.model_selection import StratifiedGroupKFold


import numpy as np
import pandas as pd
import sys

from polyssifier import poly

import logging 

import scipy.sparse as sp
import scipy.io
from scipy.stats import zscore
from scipy.signal import detrend

from scipy.sparse.linalg import eigs
from gunfolds.utils import graphkit as gk
from gunfolds.conversions import graph2adj

import matplotlib.pyplot as plt

from sklearn.preprocessing import MinMaxScaler
from sklearn.utils import check_random_state
from sklearn.impute import SimpleImputer


from sklearn.neural_network import MLPClassifier
from sklearn.metrics import roc_auc_score

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def check_matrix_powers(W, A, powers, threshold):
    for n in powers:
        W_n = np.linalg.matrix_power(W, n)
        non_zero_indices = np.nonzero(W_n)
        if (np.abs(W_n[non_zero_indices]) < threshold).any():
            return False
    return True


def create_stable_weighted_matrix(
    A,
    threshold=0.1,
    powers=[1, 2, 3, 4],
    max_attempts=1000,
    damping_factor=0.99,
    random_state=None,
):
    np.random.seed(
        random_state
    )  # Set random seed for reproducibility if provided
    attempts = 0

    while attempts < max_attempts:
        # Generate a random matrix with the same sparsity pattern as A
        random_weights = np.random.randn(*A.shape)
        weighted_matrix = A * random_weights

        # Convert to sparse format for efficient eigenvalue computation
        weighted_sparse = sp.csr_matrix(weighted_matrix)

        # Compute the largest eigenvalue in magnitude
        eigenvalues, _ = eigs(weighted_sparse, k=1, which="LM")
        max_eigenvalue = np.abs(eigenvalues[0])

        # Scale the matrix so that the spectral radius is slightly less than 1
        if max_eigenvalue > 0:
            weighted_matrix *= damping_factor / max_eigenvalue
            # Check if the powers of the matrix preserve the threshold for non-zero entries of A
            if check_matrix_powers(weighted_matrix, A, powers, threshold):
                return weighted_matrix

        attempts += 1

    raise ValueError(
        f"Unable to create a matrix satisfying the condition after {max_attempts} attempts."
    )


def drawsamplesLG(A, nstd, samples):
    n = A.shape[0]
    data = np.zeros([n, samples])
    data[:, 0] = nstd * np.random.randn(A.shape[0])
    for i in range(1, samples):
        data[:, i] = A @ data[:, i - 1] + nstd * np.random.randn(A.shape[0])
    return data


def genData(A, rate=2, burnin=100, ssize=5000, nstd=0.1):
    Agt = A.copy()
    data = drawsamplesLG(Agt, samples=burnin + (ssize * rate), nstd=nstd)
    data = data[:, burnin:]
    return data[:, ::rate]


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


#Step 0: Iterate through values for nstd, burnin, noise_svar
nstd = 1.0
burn = 100
threshold = 0.0001

NOISE_SIZE = 2961*2
NUM_SUBS = 10
subjects = ['20150210', '20150417', '20150428', '20151110', '20151127', 
            '20150410', '20150421', '20151030', '20151117', '20151204']

num_graphs = 1
num_noise = 2
n_folds = 4
n_threads= 12

graph_ix = 1002
graph_dir = '/data/users2/jwardell1/nshor_docker/examples/oulu-project/OULU/g4.pkl'
g = np.load(graph_dir, allow_pickle=True)
A = graph2adj(g)
u_rate = 1
logging.info(f'\t\t\t\tGraph Number {graph_ix} of {num_graphs}')

#SNR = 1

SNRs = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]

for noise_ix in range(num_noise):
    for SNR in SNRs:
        scalar = 10**(SNR/-2)
        logging.info(f'\t\t\t\tSNR {SNR}')
        logging.info(f'\t\t\t\tscalar {scalar}')


        num_converged = 0
        converged_subjects = []
        noises = dict()
        while num_converged < NUM_SUBS:
            for subject in subjects:
                if subject in converged_subjects:
                    continue

                try:
                    W = create_stable_weighted_matrix(A, threshold=threshold, powers=[2])
                    var_noise = genData(W, rate=u_rate, burnin=burn, ssize=NOISE_SIZE, nstd=nstd)
                    var_noise = zscore(var_noise, axis=1)
                    noises[subject] = var_noise*scalar
                    num_converged += 1
                    converged_subjects.append(subject)

                except Exception as e:
                    print(e)
                    logging.info(f'num converged: {num_converged}')
                    
        all_data = []

        with open('/data/users2/jwardell1/undersampling-project/OULU/txt-files/allsubs_TCs.txt', 'r') as tc_data:
            lines = tc_data.readlines()

        for i in range(0, len(lines), 2):
            subject = subjects[i//2]
            logging.info(f'loading TC for subject {subject}')
            filepath_sr1 = lines[i].strip()
            filepath_sr2 = lines[i+1].strip()
            try:
                sr1 = scipy.io.loadmat(filepath_sr1)['TCMax']
                sr2 = scipy.io.loadmat(filepath_sr2)['TCMax']
            
            except:
                continue

            if sr1.shape[0] != 53:
                sr1 = sr1.T

            if sr2.shape[0] != 53:
                sr2 = sr2.T
            
            if sr1.shape[1] < sr2.shape[1]:
                tr100_tc = sr2
                tr2150_tc = sr1
            else:
                tr100_tc = sr1
                tr2150_tc = sr2

            logging.info(f'subject {subject} tr100_tc.shape - {tr100_tc.shape}')
            logging.info(f'subject {subject} tr2150_tc.shape - {tr2150_tc.shape}')

            tr100_tc_zs = zscore(tr100_tc, axis=1)
            tr2150_tc_zs = zscore(tr2150_tc, axis=1)

            tr100_tc_zs_dt = detrend(tr100_tc_zs, axis=1)
            tr2150_tc_zs_dt = detrend(tr2150_tc_zs, axis=1)

            noise_tr100 = noises[subject][:,::2]
            noise_tr2150 = noises[subject][:,::33]

            tr100_tc_zs_dt_noise = tr100_tc_zs_dt+noise_tr100
            tr2150_tc_zs_dt_noise = tr2150_tc_zs_dt+noise_tr2150

            all_data.append({'Subject_ID'             : str(subject), 
                            'VAR_Noise'               : noises[subject], 
                            'TR100_Noise'             : noise_tr100, 
                            'TR2150_Noise'            : noise_tr2150, 
                            'TR100_Timecourse'        : tr100_tc_zs_dt, 
                            'TR2150_Timecourse'       : tr2150_tc_zs_dt, 
                            'TR100_Timecourse_Noise'  : tr100_tc_zs_dt_noise, 
                            'TR2150_Timecourse_Noise' : tr2150_tc_zs_dt_noise})
            
        data_df = pd.DataFrame(all_data)

        tr100_data = []
        tr2150_data = []
        add_data = []
        concat_data = []

        for subject in subjects:
            sub_row = data_df[data_df['Subject_ID']  == subject]
            logging.info(f'subject {subject}')

            tr100 = sub_row['TR100_Timecourse'].iloc[0]
            tr100_noise = sub_row['TR100_Timecourse_Noise'].iloc[0]
            
            tr2150 = sub_row['TR2150_Timecourse'].iloc[0]
            tr2150_noise = sub_row['TR2150_Timecourse_Noise'].iloc[0]

            n_regions, n_tp_tr100 = tr100.shape
            _, n_tp_tr2150 = tr2150.shape

            tr2150_window_size = 100
            tr2150_stride = 1
            n_sections = 80
            tr2150_start_ix = 0
            tr2150_end_ix = tr2150_window_size
            
            tr100_window_size = int((n_tp_tr100 / n_tp_tr2150) * tr2150_window_size)
            tr100_stride = n_tp_tr100 // n_tp_tr2150
            tr100_start_ix = 0
            tr100_end_ix = tr100_window_size


            for j in range(n_sections):
                window_ix = i * n_sections * 2 + j * 2
                
                tr100_section = tr100[:, tr100_start_ix:tr100_end_ix]
                tr100_section_noise = tr100_noise[:, tr100_start_ix:tr100_end_ix]

                tr2150_section = tr2150[:, tr2150_start_ix:tr2150_end_ix]
                tr2150_section_noise = tr100_noise[:, tr2150_start_ix:tr2150_end_ix]






                tr100_fnc_triu = np.corrcoef(tr100_section)[np.triu_indices(n_regions)]
                tr100_noise_fnc_triu = np.corrcoef(tr100_section_noise)[np.triu_indices(n_regions)]

                tr2150_fnc_triu = np.corrcoef(tr2150_section)[np.triu_indices(n_regions)]
                tr2150_noise_fnc_triu = np.corrcoef(tr2150_section_noise)[np.triu_indices(n_regions)]

                concat_tr100_tr2150 = np.concatenate((tr100_fnc_triu , tr2150_fnc_triu))
                concat_tr100_tr2150_noise = np.concatenate((tr100_noise_fnc_triu , tr2150_noise_fnc_triu))

                add_tr100_tr2150 = tr100_fnc_triu + tr2150_fnc_triu
                add_tr100_tr2150_noise = tr100_noise_fnc_triu + tr2150_noise_fnc_triu


                tr100_data.append({'subject'          : subject, 
                                   'TR100ms_Window'   : tr100_fnc_triu, 
                                   'target'           : '0'})
                tr100_data.append({'subject'          : subject, 
                                   'TR100ms_Window'   : tr100_noise_fnc_triu, 
                                   'target'           : '1'})
                
                tr2150_data.append({'subject'         : subject,
                                    'TR2150ms_Window' : tr2150_fnc_triu, 
                                    'target'          : '0'})
                tr2150_data.append({'subject'         : subject,
                                    'TR2150ms_Window' : tr2150_noise_fnc_triu, 
                                    'target'          : '1'})
                
                concat_data.append({'subject'         : subject, 
                                    'Concat_Window'   : concat_tr100_tr2150,
                                   'target'           : '0'})
                concat_data.append({'subject'         : subject, 
                                   'Concat_Window'    : concat_tr100_tr2150_noise,
                                   'target'           : '1'})
                
                add_data.append({'subject'            : subject,
                                 'Add_Window'         : add_tr100_tr2150,
                                 'target'             : '0'})
                add_data.append({'subject'            : subject,
                                 'Add_Window'         : add_tr100_tr2150,
                                 'target'             : '1'})
                
                tr100_start_ix += tr100_stride
                tr100_end_ix = tr100_end_ix + tr100_stride
                    
                tr2150_start_ix += tr2150_stride
                tr2150_end_ix = tr2150_end_ix + tr2150_stride



        tr100_df = pd.DataFrame(tr100_data)
        tr2150_df = pd.DataFrame(tr2150_data)
        concat_df = pd.DataFrame(concat_data)
        add_df = pd.DataFrame(add_data)


#############################
#   TR=100ms
#############################
        logging.info(f'\n\n\n\n START POLYSSIFIER FOR TR=100ms snr {SNR} scalar {scalar} noise_ix {noise_ix}')
        group_tr100 = tr100_df['subject']
        y_tr100 = tr100_df['target']
        y_tr100 = np.array([str(entry) for entry in y_tr100])
        X_tr100 = tr100_df['TR100ms_Window']
        X_tr100 = np.array([np.array(entry) for entry in X_tr100])

        res1 = []
        report1 = poly(data=X_tr100, label=y_tr100, groups=group_tr100, n_folds=n_folds, scale=True, concurrency=n_threads, save=False, 
                        exclude=['Decision Tree', 'Random Forest', 'Voting', 'Nearest Neighbors', 'Linear SVM'],  scoring='auc')

        for classifier in report1.scores.columns.levels[0]:
                    if classifier == 'Voting':
                        continue

                    res1.append({'graph_no': graph_ix,
                                    'nstd': nstd,
                                    'burnin': burn,
                                    'noise_no': noise_ix,
                                    'snr': SNR,
                                    'scalar': scalar,
                                    'classifier': classifier,
                                    'test_scores': report1.scores[classifier, 'test'], 
                                    'target': report1.target, 
                                    'predictions': np.array(report1.predictions[classifier]).astype(int),
                                    'test_proba': report1.test_proba[classifier]})

                    logging.info(report1.scores[classifier, 'test'])

#############################
#   TR=2150ms
#############################
        logging.info(f'\n\n\n\n START POLYSSIFIER FOR TR=2150ms snr {SNR} scalar {scalar} noise_ix {noise_ix}')
        group_tr2150 = tr2150_df['subject']
        y_tr2150 = tr2150_df['target']
        y_tr2150 = np.array([str(entry) for entry in y_tr2150])
        X_tr2150 = tr2150_df['TR2150ms_Window']
        X_tr2150 = np.array([np.array(entry) for entry in X_tr2150])

        res2 = []
        report2 = poly(data=X_tr2150, label=y_tr2150, groups=group_tr2150, n_folds=n_folds, scale=True, concurrency=n_threads, save=False, 
                        exclude=['Decision Tree', 'Random Forest', 'Voting', 'Nearest Neighbors', 'Linear SVM'],  scoring='auc')

        for classifier in report2.scores.columns.levels[0]:                                                                                         # iterate through all classifiers in the report
                    if classifier == 'Voting':
                        continue

                    res2.append({'graph_no': graph_ix,                                                                                                      # save the SR1 results to a dict for results dataframe
                                    'nstd': nstd,
                                    'burnin': burn,
                                    'noise_no': noise_ix,
                                    'snr': SNR,
                                    'scalar': scalar,
                                    'classifier': classifier,
                                    'test_scores': report2.scores[classifier, 'test'], 
                                    'target': report2.target, 
                                    'predictions': np.array(report2.predictions[classifier]).astype(int),
                                    'test_proba': report2.test_proba[classifier]})

                    logging.info(report2.scores[classifier, 'test'])


#############################
#   CONCAT
#############################
        logging.info(f'\n\n\n\n START POLYSSIFIER FOR CONCAT snr {SNR} scalar {scalar} noise_ix {noise_ix}')
        group_concat = concat_df['subject']
        y_concat = concat_df['target']
        y_concat = np.array([str(entry) for entry in y_concat])
        X_concat = concat_df['Concat_Window']
        X_concat = np.array([np.array(entry) for entry in X_concat])

        res3 = []
        report3 = poly(data=X_concat, label=y_concat, groups=group_concat, n_folds=n_folds, scale=True, concurrency=n_threads, save=False, 
                        exclude=['Decision Tree', 'Random Forest', 'Voting', 'Nearest Neighbors', 'Linear SVM'],  scoring='auc')

        for classifier in report3.scores.columns.levels[0]:                                                                                         # iterate through all classifiers in the report
                    if classifier == 'Voting':
                        continue

                    res3.append({'graph_no': graph_ix,                                                                                                      # save the SR1 results to a dict for results dataframe
                                    'nstd': nstd,
                                    'burnin': burn,
                                    'noise_no': noise_ix,
                                    'snr': SNR,
                                    'scalar': scalar,
                                    'classifier': classifier,
                                    'test_scores': report3.scores[classifier, 'test'], 
                                    'target': report3.target, 
                                    'predictions': np.array(report3.predictions[classifier]).astype(int),
                                    'test_proba': report3.test_proba[classifier]})

                    logging.info(report3.scores[classifier, 'test'])

#############################
#   ADD
#############################
        logging.info(f'\n\n\n\n START POLYSSIFIER FOR ADD snr {SNR} scalar {scalar} noise_ix {noise_ix}')
        group_add = add_df['subject']
        y_add = add_df['target']
        y_add = np.array([str(entry) for entry in y_add])
        X_add = add_df['Add_Window']
        X_add = np.array([np.array(entry) for entry in X_add])

        res4 = []
        report4 = poly(data=X_add, label=y_add, groups=group_add, n_folds=n_folds, scale=True, concurrency=n_threads, save=False, 
                        exclude=['Decision Tree', 'Random Forest', 'Voting', 'Nearest Neighbors', 'Linear SVM'],  scoring='auc')

        for classifier in report4.scores.columns.levels[0]:                                                                                         # iterate through all classifiers in the report
                    if classifier == 'Voting':
                        continue

                    res4.append({'graph_no': graph_ix,                                                                                                      # save the SR1 results to a dict for results dataframe
                                    'nstd': nstd,
                                    'burnin': burn,
                                    'noise_no': noise_ix,
                                    'snr': SNR,
                                    'scalar': scalar,
                                    'classifier': classifier,
                                    'test_scores': report4.scores[classifier, 'test'], 
                                    'target': report4.target, 
                                    'predictions': np.array(report4.predictions[classifier]).astype(int),
                                    'test_proba': report4.test_proba[classifier]})

                    logging.info(report4.scores[classifier, 'test'])





df1 = pd.DataFrame(res1)                                                                                    # save SR1 results as dataframe
df2 = pd.DataFrame(res2)                                                                                    # save SR2 results as dataframe
df3 = pd.DataFrame(res3)                                                                                    # save CONCAT results as dataframe
df4 = pd.DataFrame(res4)                                                                                    # save ADD results as dataframe



df1.to_pickle(f'/data/users2/jwardell1/undersampling-project/OULU/pkl-files/sr1_{SNR}_{graph_ix}.pkl')      # write SR1 dataframe to disk as pickle
df2.to_pickle(f'/data/users2/jwardell1/undersampling-project/OULU/pkl-files/sr2_{SNR}_{graph_ix}.pkl')      # write SR2 dataframe to disk as pickle
df3.to_pickle(f'/data/users2/jwardell1/undersampling-project/OULU/pkl-files/concat_{SNR}_{graph_ix}.pkl')   # write CONCAT dataframe to disk as pickle
df4.to_pickle(f'/data/users2/jwardell1/undersampling-project/OULU/pkl-files/add_{SNR}_{graph_ix}.pkl')      # write ADD dataframe to disk as pickle

