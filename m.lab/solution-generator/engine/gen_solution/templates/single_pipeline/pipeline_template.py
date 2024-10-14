import os 


def inference(alo_context: dict, alo_pipeline: dict, arg_0):
    logger = alo_context['logger']
    logger.info("===== single pipeline start =====")
    # read data from data_path 
    data_path = alo_pipeline['dataset']['workspace'] + '/'

    # run train 
    
    # run inference 
    
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