import os 
import warnings
warnings.filterwarnings("ignore")
 

def alo_train(alo_context: dict, alo_pipeline: dict, alo_sample_arg):
    logger = alo_context['logger']
    logger.info("===== train start =====") 
    # read data from train_data_path 
    train_data_path = alo_pipeline['dataset']['workspace'] + '/'
    
    # train model


    # save model file into model_path 
    model_path = alo_context['model']['workspace'] + '/'


def alo_inference(alo_context: dict, alo_pipeline: dict, alo_sample_arg):
    logger = alo_context['logger']
    logger.info("===== inference start =====")
    # read data from inference_data_path 
    inference_data_path = alo_pipeline['dataset']['workspace'] + '/'

    # load trained model file from model_path 
    model_path = alo_context['model']['workspace'] + '/'

    # run inference with loaded model


    # save inference output file to output_path 
    output_path = alo_pipeline['artifact']['workspace'] + '/'

    # save inference summary 
    return { 
        'summary': {
            'result': result,
            'note': note,
            'score': score
        }
    }


