import numpy as np
import pandas as pd
import sys

from polyssifier import poly

import logging 

import scipy.io
from scipy.stats import zscore
import scipy.signal


from sklearn.preprocessing import MinMaxScaler
from sklearn.utils import check_random_state
from sklearn.impute import SimpleImputer

import scipy.sparse as sp
from scipy.sparse.linalg import eigs
from gunfolds.utils import graphkit as gk
from gunfolds.conversions import graph2adj


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


def genData(A, rate=2, burnin=100, ssize=5000, nstd=1):
    Agt = A.copy()
    data = drawsamplesLG(Agt, samples=burnin + (ssize * rate), nstd=nstd)
    data = data[:, burnin:]
    return data[:, ::rate]



"""
if len(sys.argv) != 4:
    print("Usage: python poly_noise1.py SNR graph_dir graph_ix")
    sys.exit(1)

SNR = float(sys.argv[1])
graph_dir = sys.argv[2]
graph_ix = int(sys.argv[3])
g = np.load(graph_dir, allow_pickle=True)
"""
SNRs = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
graph_ix = 1000
graph_dir = '/data/users2/jwardell1/nshor_docker/examples/oulu-project/OULU/g0.pkl'
g = np.load(graph_dir, allow_pickle=True)#= gk.ringmore(53, 10)



num_converged = 0
noises = dict()
converged_subjects = []


#g = gk.ringmore(53, 10)
g = np.load(graph_dir, allow_pickle=True)


num_graphs = 3
num_noise = 3
n_folds = 4
n_threads= 16


nstd = 1.0
burn = 100
threshold = 0.0001
NOISE_SIZE = 1200


subjects = np.loadtxt("/data/users2/jwardell1/undersampling-project/HCP/txt-files/subjects.txt", dtype=str)
#subjects = np.loadtxt("/data/users2/jwardell1/undersampling-project/HCP/txt-files/subjects_dbg.txt", dtype=str)


noises = dict()





res1 = []
res2 = []
res3 = []
res4 = []












A = graph2adj(g)
u_rate = 1
logging.info(f'\t\t\t\tGraph Number {graph_ix} of {num_graphs}')

#Using the loaded graph, generate a number of noise matrices for all subjects until converged
for noise_ix in range(num_noise):
    for SNR in SNRs:
        scalar = 10**(SNR/-2)

        logging.info(f'\t\t\t\tSNR- {SNR}')
        logging.info(f'\t\t\t\tscalar- {scalar}')
        logging.info(f'\t\t\t\tGRAPH IX- {graph_ix}')
        num_converged = 0
        noises = dict()
        converged_subjects = []
        while num_converged < len(subjects):
            for subject in subjects:
                if subject in converged_subjects:
                    continue  


                try:
                    W = create_stable_weighted_matrix(A, threshold=0.001, powers=[2])
                    var_noise = genData(W, rate=u_rate, burnin=burn, ssize=NOISE_SIZE, nstd=nstd)
                    var_noise = zscore(var_noise, axis=1)
                    noises[subject] = var_noise*scalar
                    num_converged += 1
                    converged_subjects.append(subject)
                
                except Exception as e:
                    print(f'Convergence error while generating matrix for dir {subject}, num converged: {num_converged}')
                    print(e)
                    continue
            


        #Load all subject time courses, add noise and perform windowing
        with open('/data/users2/jwardell1/undersampling-project/HCP/txt-files/tc_data.txt', 'r') as tc_data:
        #with open('/data/users2/jwardell1/undersampling-project/HCP/txt-files/tc_data_dbg.txt', 'r') as tc_data:
            lines = tc_data.readlines()
        
        fnc_sr1 = []
        fnc_sr2 = []
        fnc_concat = []
        fnc_add = []

        for i in range(len(lines)):
            file_path_sr1 = lines[i].strip()
            logging.info(f'Processing SR1: {file_path_sr1}')
            try:
                sr1 = scipy.io.loadmat(file_path_sr1)['TCMax']
            except:
                continue

            
            

            if sr1.shape[0] != 53:
                sr1 = sr1.T

            if sr1.shape[1] < 1200:
                continue

            logging.info(f'sr1.shape - {sr1.shape}')
            sr1 = zscore(sr1, axis=1)
            sr1 = scipy.signal.detrend(sr1, axis=1)
            sr2 = sr1[:,::3]
            logging.info(f'sr2.shape - {sr2.shape}')


            n_regions = sr1.shape[0]

            subject_id = file_path_sr1.split('/')[-3]
            var_noise = noises[subject_id]

            fnc_sr1.append((np.corrcoef(sr1)[np.triu_indices(n_regions)], 0, subject_id))
            fnc_sr1.append((np.corrcoef(sr1 + var_noise)[np.triu_indices(n_regions)], 1, subject_id))

            fnc_sr2.append((np.corrcoef(sr2)[np.triu_indices(n_regions)], 0, subject_id))
            fnc_sr2.append((np.corrcoef(sr2 + var_noise[:,::3])[np.triu_indices(n_regions)], 1, subject_id))

            window_ix = len(fnc_sr1)-2
            logging.info(f'window_ix {window_ix}')
            logging.info(f'len(fnc_sr1) {len(fnc_sr1)}')
            logging.info(f'len(fnc_sr2) {len(fnc_sr2)}')

            fnc_concat.append((np.concatenate((fnc_sr1[window_ix][0], fnc_sr2[window_ix][0])), 0, subject_id))
            fnc_concat.append((np.concatenate((fnc_sr1[window_ix+1][0], fnc_sr2[window_ix+1][0])), 1, subject_id))

            fnc_add.append(((fnc_sr1[window_ix][0] + fnc_sr2[window_ix][0]), 0, subject_id))
            fnc_add.append(((fnc_sr1[window_ix+1][0] + fnc_sr2[window_ix+1][0]), 1, subject_id))



        #Prepare the data for polyssifier
        data_sr1 = [entry[0] for entry in fnc_sr1]
        labels_sr1 = [entry[1] for entry in fnc_sr1]
        groups_sr1 = [entry[2] for entry in fnc_sr1]

        data_sr2 = [entry[0] for entry in fnc_sr2]
        labels_sr2 = [entry[1] for entry in fnc_sr2]
        groups_sr2 = [entry[2] for entry in fnc_sr2]

        data_concat = [entry[0] for entry in fnc_concat]
        labels_concat = [entry[1] for entry in fnc_concat]
        groups_concat = [entry[2] for entry in fnc_concat]

        data_add = [entry[0] for entry in fnc_add]
        labels_add = [entry[1] for entry in fnc_add]
        groups_add = [entry[2] for entry in fnc_add]
        
        
        
        # Initialize SimpleImputer
        imputer = SimpleImputer(strategy='mean')

        # Impute missing values and encode labels for each dataset
        data_sr1 = imputer.fit_transform(data_sr1)
        data_sr2 = imputer.fit_transform(data_sr2)
        data_concat = imputer.fit_transform(data_concat)
        data_add = imputer.fit_transform(data_add)


        np.random.seed(42)
        random_state = check_random_state(42)


        scaler1 = MinMaxScaler()#StandardScaler()
        data_scaled1 = scaler1.fit_transform(data_sr1)

        scaler2 = MinMaxScaler()#StandardScaler()
        data_scaled2 = scaler2.fit_transform(data_sr2)

        scaler3 = MinMaxScaler()#StandardScaler()
        data_scaled3 = scaler3.fit_transform(data_concat)

        scaler4 = MinMaxScaler()#StandardScaler()
        data_scaled4 = scaler4.fit_transform(data_add)



        #Run polyssifer for each sampling rate
        report1 = poly(data_scaled1, np.array(labels_sr1), n_folds=10, scale=True, random_state=random_state,
                            exclude=['Decision Tree', 'Random Forest', 'Voting', 'Nearest Neighbors', 'Linear SVM'],
                            scoring='auc', project_name=f'SR1_noise_{scalar}', concurrency=32, verbose=True)
        

        report2 = poly(data_scaled2, np.array(labels_sr2), n_folds=10, scale=True, random_state=random_state,
                            exclude=['Decision Tree', 'Random Forest', 'Voting', 'Nearest Neighbors', 'Linear SVM'], 
                            scoring='auc', project_name=f'SR2_noise_{scalar}', concurrency=32, verbose=True)
        
        report3 = poly(data_scaled3, np.array(labels_concat), n_folds=10, scale=True, random_state=random_state,
                            exclude=['Decision Tree', 'Random Forest', 'Voting', 'Nearest Neighbors', 'Linear SVM'],
                            scoring='auc', project_name=f'CONCAT_noise_{scalar}', concurrency=32, verbose=True)
        
        report4 = poly(data_scaled4, np.array(labels_add), n_folds=10, scale=True, random_state=random_state,
                            exclude=['Decision Tree', 'Random Forest', 'Voting', 'Nearest Neighbors', 'Linear SVM'],
                            scoring='auc', project_name=f'CONCAT_noise_{scalar}', concurrency=32, verbose=True)
        




        #Collect results for saving
        for classifier in report1.scores.columns.levels[0]:
            if classifier == 'Voting':
                continue

            # Append the results to the list as a dictionary
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
        
        for classifier in report2.scores.columns.levels[0]:
            if classifier == 'Voting':
                continue

            # Append the results to the list as a dictionary
            res2.append({'graph_no': graph_ix,
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
        
        for classifier in report3.scores.columns.levels[0]:
            if classifier == 'Voting':
                continue

            # Append the results to the list as a dictionary
            res3.append({'graph_no': graph_ix,
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
        
        for classifier in report4.scores.columns.levels[0]:
            if classifier == 'Voting':
                continue

            # Append the results to the list as a dictionary
            res4.append({'graph_no': graph_ix,
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

#Populate dataframes and save
df1 = pd.DataFrame(res1)
df2 = pd.DataFrame(res2)
df3 = pd.DataFrame(res3)
df4 = pd.DataFrame(res4)
df1.to_pickle(f'/data/users2/jwardell1/undersampling-project/HCP/pkl-files/sr1_{SNR}_{graph_ix}.pkl')
df2.to_pickle(f'/data/users2/jwardell1/undersampling-project/HCP/pkl-files/sr2_{SNR}_{graph_ix}.pkl')
df3.to_pickle(f'/data/users2/jwardell1/undersampling-project/HCP/pkl-files/concat_{SNR}_{graph_ix}.pkl')
df4.to_pickle(f'/data/users2/jwardell1/undersampling-project/HCP/pkl-files/add_{SNR}_{graph_ix}.pkl')