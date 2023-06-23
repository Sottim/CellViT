[![Python 3.9.7](https://img.shields.io/badge/python-3.9.7-blue.svg)](https://www.python.org/downloads/release/python-360/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Flake8 Status](./reports/flake8/flake8-badge.svg)](./reports/flake8/index.html)
<img src="https://img.shields.io/badge/PyTorch-EE4C2C?style=flat-square&logo=Pytorch&logoColor=white"/></a>
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
___
<p align="center">
  <img src="./docs/figures/banner.png"/>
</p>

___

# CellViT: Expanding Horizons with Vision Transformers for Precise Cell Segmentation and Classification
This is the official PyTorch implementation of the cell detection and instance segmentation algorithm using a comination of Vision Transformer image encoder and U-Net network structure, titled: "CellViT: Expanding Horizons with Vision Transformers for Precise Cell Segmentation and Classification" (Fabian Hörst, Moritz Rempe, Lukas Heine, Constantin Seibold, Julius Keyl, Giulia Baldini, Selma Ugurel, Jens Siveke, Barbara Grünwald, Jan Egger, and Jens Kleesiek, 2023)

This repository contains the code implementation of CellViT, a deep learning-based method for automated instance segmentation of cell nuclei in digitized tissue samples. CellViT utilizes a Vision Transformer architecture and achieves state-of-the-art performance on the PanNuke dataset, a challenging nuclei instance segmentation benchmark.

<p align="center">
  <img src="./docs/figures/network_large.png"/>
</p>


## Key Features
- Utilizes Vision Transformer (ViT) for nuclei instance segmentation.
- Trained and evaluated on the PanNuke dataset, a challenging nuclei segmentation benchmark.
– Achieves state-of-the-art performance on the PanNuke dataset:
  - Mean panoptic quality: 0.51
  - F1-detection score: 0.83

![Example](docs/figures/overlay.gif)

## Installation

1. Clone the repository:
  `git clone https://github.com/TIO-IKIM/CellViT.git`
2. Create a conda environment with Python 3.9.7 version and install conda requirements: `conda create --name pathology_env --file ./requirements_conda.txt python=3.9.7`
3. Activate environment: `conda activate pathology_env`
4. Install torch for for system, as described [here](https://pytorch.org/get-started/locally/). Preferred version is 1.13, see [optional_dependencies](./optional_dependencies.txt) for help.
5. Install pip dependencies: `pip install -r requirements.txt`
---
Optional:
Install optional dependencies `pip install -r optional_dependencies.txt` to get a speedup using [NVIDIA-Clara](https://www.nvidia.com/de-de/clara/) and [CuCIM](https://github.com/rapidsai/cucim)
for preprocessing during inference.


## Usage:


Model checkpoints can be downloaded here:

- [CellViT-SAM-H](https://drive.google.com/uc?export=download&id=1MvRKNzDW2eHbQb5rAgTEp6s2zAXHixRV) 🚀
- [CellViT-256](https://drive.google.com/uc?export=download&id=1tVYAapUo1Xt8QgCN22Ne1urbbCZkah8q)
- [CellViT-SAM-H-x20](https://drive.google.com/uc?export=download&id=1wP4WhHLNwyJv97AK42pWK8kPoWlrqi30)
- [CellViT-256-x20](https://drive.google.com/uc?export=download&id=1w99U4sxDQgOSuiHMyvS_NYBiz6ozolN2)

License: [Apache 2.0 with Commons Clause](./LICENSE)

Pre-trained ViT models for training initialization can be downloaded here: [ViT-Models](https://drive.google.com/drive/folders/1zFO4bgo7yvjT9rCJi_6Mt6_07wfr0CKU?usp=sharing)
Please check out the corresponding licenses before distribution and further usage!


## Folder Structure
We are currently using the following folder structure:

```bash
├── base_ml               # Basic Machine Learning Code: CLI, Trainer, Experiment, ...
├── configs               # Config files
│   ├── examples            # Example config files with explanations
│   ├── projects            # Project specific configuration file (e.g., Cell detection)
│   └── python              # Python configuration file for global Python settings
├── datamodel             # Datamodels of WSI, Patientes etc. (not ML specific)
├── docs                  # Documentation files (in addition to this main README.md)
├── file_handling         # File handling code, e.g., for creating splits
├── models                # Machine Learning Models (PyTorch implementations)
│   ├── decoders            # Decoder networks (see ML structure below)
│   ├── encoders            # Encoder networks (see ML structure below)
│   ├── pretrained          # Checkpoint of important pretrained models
├── notebooks             # Folder for additional notebooks
├── preprocessing         # Preprocessing code
│   ├── encoding            # Encoding code to create embeddings of patches
│   └── patch_extraction    # Code to extract patches from WSI
├── test_database         # Test database for testing purposes
│   ├── examples            # Example files
│   ├── input               # WSI files and annotations
├── tests                 # Unittests
```


### Preprocessing
Whole-slide image preprocessing is an essential step in digital pathology that involves preparing digital images of entire tissue slides for analysis by pathologists and machine learning algorithms. Whole-slide images are typically high-resolution digital images of tissue slides, which can range in size from hundreds of megabytes to several gigabytes. The large size of these images presents a challenge for analysis, as processing them directly can be computationally intensive and time-consuming.

Preprocessing whole-slide images typically involves dividing the images into smaller, more manageable patches or tiles. These patches are typically square or rectangular, and can be selected using a regular grid pattern or using more sophisticated methods that take into account the content of the image. Once the patches are extracted, various techniques can be applied to improve the quality and consistency of the image data.

In our Pre-Processing pipeline, we are able to extract quadratic patches from detected tissue areas, load annotation files (`.json`) and apply color normlizations. We make use of the popular [OpenSlide](https://openslide.org/) library, but extended it with the [RAPIDS cuCIM](https://github.com/rapidsai/cucim) framework for an x8 speedup in patch-extraction.

The documentation for the preprocessing can be found [here](./docs/readmes/preprocessing.md).

### Resulting Dataset Structure
In general, the folder structure for a preprocessed dataset looks like this:
The aim of pre-processing is to create one dataset per WSI in the following structure:
```bash
WSI_Name
├── annotation_masks      # thumbnails of extracted annotation masks
│   ├── all_overlaid.png  # all with same dimension as the thumbnail
│   ├── tumor.png
│   └── ...  
├── context               # context patches, if extracted
│   ├── 2                 # subfolder for each scale
│   │   ├── WSI_Name_row1_col1_context_2.png
│   │   ├── WSI_Name_row2_col1_context_2.png
│   │   └── ...
│   └── 4
│   │   ├── WSI_Name_row1_col1_context_2.png
│   │   ├── WSI_Name_row2_col1_context_2.png
│   │   └── ...
├── masks                 # Mask (numpy) files for each patch -> optional folder for segmentation
│   ├── WSI_Name_row1_col1.npy
│   ├── WSI_Name_row2_col1.npy
│   └── ...
├── metadata              # Metadata files for each patch
│   ├── WSI_Name_row1_col1.yaml
│   ├── WSI_Name_row2_col1.yaml
│   └── ...
├── patches               # Patches as .png files
│   ├── WSI_Name_row1_col1.png
│   ├── WSI_Name_row2_col1.png
│   └── ...
├── thumbnails            # Different kind of thumbnails
│   ├── thumbnail_mpp_5.png
│   ├── thumbnail_downsample_32.png
│   └── ...
├── tissue_masks          # Tissue mask images for checking
│   ├── mask.png          # all with same dimension as the thumbnail
│   ├── mask_nogrid.png
│   └── tissue_grid.png
├── mask.png              # tissue mask with green grid  
├── metadata.yaml         # WSI metdata for patch extraction
├── patch_metadata.json   # Patch metadata of WSI merged in one file
└── thumbnail.png         # WSI thumbnail
```
For later usage with two-stage models (see [Encoding](#encoding) section), another folder is created for slide-embeddings:
```bash
WSI_Name
├── annotation_masks  
│   └── ...  
├── embeddings          # Embeddings of the WSI
│   ├── # Embedding vector for all patches as torch tensor with given backbone name and comment (defined during encoding phase)
│   ├── # Each embedding vector has the shape [num_patches, embedding_dimension]
│   ├── embedding_{backbone+comment}.pt  
│   ├── # Important metadata such like row, col position of each patch, wsi_metadata, intersected labels etc.
│   ├── embedding_{backbone+comment}_metadata.json
...
```

#### CLI
The CLI for a ML-experiment is as follows (here the [```run_clam.py```](./classification/run_clam.py) script is used):
```bash
usage: run_clam.py [-h] --config CONFIG [--gpu GPU] [--sweep | --agent AGENT | --checkpoint CHECKPOINT]

Start an experiment with given configuration file.

optional arguments:
  -h, --help            show this help message and exit
  --gpu GPU             Cuda-GPU ID (default: None)
  --sweep               Starting a sweep. For this the configuration file must be structured according to WandB sweeping. Compare
                        https://docs.wandb.ai/guides/sweeps and https://community.wandb.ai/t/nested-sweep-configuration/3369/3 for further
                        information. This parameter cannot be set in the config file! (default: False)
  --agent AGENT         Add a new agent to the sweep. Please pass the sweep ID as argument in the way entity/project/sweep_id, e.g.,
                        user1/test_project/v4hwbijh. The agent configuration can be found in the WandB dashboard for the running sweep in
                        the sweep overview tab under launch agent. Just paste the entity/project/sweep_id given there. The provided config
                        file must be a sweep config file.This parameter cannot be set in the config file! (default: None)
  --checkpoint CHECKPOINT
                        Path to a PyTorch checkpoint file. The file is loaded and continued to train with the provided settings. If this is
                        passed, no sweeps are possible. This parameter cannot be set in the config file! (default: None)

required named arguments:
  --config CONFIG       Path to a config file (default: None)
```

The important file is the configuration file, in which all paths are set, the model configuration is given and the hyperparameters or sweeps are defined. For each specific run file, there exists an example file in the [./configs/examples/classification](./configs/examples/classification) folder with the same naming as well as a configuration file that explains how to run WandB sweeps for hyperparameter search. A general configuration for all experiments is given one section below.

All metrics defined in your trainer are logged to WandB. The WandB configuration needs to be set up in the configuration file.

!!!! Insert link to example yaml file!!!!!