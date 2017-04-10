import numpy as np
from concise.utils.fasta import write_fasta, iter_fasta
from concise.preprocessing.sequence import pad_sequences
from subprocess import call
import os
from pkg_resources import resource_filename

from multiprocessing import Pool
import multiprocessing


RNAplfold_BIN_DIR = os.path.dirname(resource_filename('concise', 'resources/RNAplfold/E_RNAplfold'))
RNAplfold_PROFILES_EXECUTE = ["H", "I", "M", "E"]
RNAplfold_PROFILES = ["Pairedness", "Hairpin loop", "Internal loop", "Multi loop", "External region"]


def run_RNAplfold(input_fasta, tmpdir, W=240, L=160, U=1):
    """
    Arguments:
       W, Int: span - window length
       L, Int, maxiumm span
       U, Int, size of unpaired region
    """

    profiles = RNAplfold_PROFILES_EXECUTE
    for i, P in enumerate(profiles):
        print("running {P}_RNAplfold... ({i}/{N})".format(P=P, i=i + 1, N=len(profiles)))

        command = "{bin}/{P}_RNAplfold".format(bin=RNAplfold_BIN_DIR, P=P)
        file_out = "{tmp}/{P}_profile.fa".format(tmp=tmpdir, P=P)
        args = " -W {W} -L {L} -u {U} < {fa} > {file_out}".format(W=W, L=L, U=U, fa=input_fasta, file_out=file_out)

        os.system(command + args)

        if os.path.getsize(file_out) == 0:
            raise Exception("command wrote an empty file: {0}".format(file_out))
        # TODO - check if the file is empty
    print("done!")


def read_RNAplfold(tmpdir, maxlen=None, seq_align="start", pad_with="E"):
    """
    pad_with = with which 2ndary structure should we pad the sequence?
    """
    assert pad_with in {"P", "H", "I", "M", "E"}

    def read_profile(tmpdir, P):
        return [values.strip().split("\t")
                for seq_name, values in iter_fasta("{tmp}/{P}_profile.fa".format(tmp=tmpdir, P=P))]

    def nelem(P, pad_width):
        """get the right neutral element
        """
        return 1 if P is pad_with else 0

    arr_hime = np.array([pad_sequences(read_profile(tmpdir, P),
                                       value=[nelem(P, pad_with)],
                                       align=seq_align,
                                       maxlen=maxlen)
                         for P in RNAplfold_PROFILES_EXECUTE], dtype="float32")

    # add the pairness column
    arr_p = 1 - arr_hime.sum(axis=0)[np.newaxis]
    arr = np.concatenate((arr_p, arr_hime))

    # reshape to: seq, seq_length, num_channels
    arr = np.moveaxis(arr, 0, 2)
    return arr


def encodeRNAStructure_parallel(seq_vec, maxlen=None, seq_align="start",
                                W=240, L=160, U=1, n_cores=4,
                                tmpdir="/tmp/RNAplfold/"):

    if maxlen is None:
        maxlen = max([len(seq) for seq in seq_vec])
    n_cores = min(len(seq_vec), n_cores, multiprocessing.cpu_count())

    p = Pool(n_cores)
    job_args = [(seq_vec[i::n_cores], maxlen, seq_align, W, L, U, "{0}/job_{1}".format(tmpdir, i))
                for i in range(n_cores)]

    results = p.map(wrap_encodeRNAStructure, job_args)
    return np.concatenate(results)


def wrap_encodeRNAStructure(args):
    return encodeRNAStructure(*args)


def encodeRNAStructure(seq_vec, maxlen=None, seq_align="start",
                       W=240, L=160, U=1,
                       tmpdir="/tmp/RNAplfold/"):
    """
    Arguments:
       W, Int: span - window length
       L, Int, maxiumm span
       U, Int, size of unpaired region

    Recomendation:
    - for human, mouse use W, L, u : 240, 160, 1
    - for fly, yeast   use W, L, u :  80,  40, 1

    """
    if not isinstance(seq_vec, list):
        seq_vec = seq_vec.tolist()
    if not os.path.exists(tmpdir):
        os.makedirs(tmpdir)

    fasta_path = tmpdir + "/input.fasta"
    write_fasta(fasta_path, seq_vec)
    run_RNAplfold(fasta_path, tmpdir, W=W, L=L, U=U)
    # 1. split the fasta into pieces
    # 2. run_RNAplfold for each of them
    # 3. Read the results
    return read_RNAplfold(tmpdir, maxlen, seq_align=seq_align, pad_with="E")
