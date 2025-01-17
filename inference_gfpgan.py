import argparse
import cv2
import glob
import numpy as np
import os
import torch
from basicsr.utils import imwrite
import logging



logging.basicConfig(level=logging.INFO, format=f'%(asctime)s %(threadName)s %(levelname)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)

from common.shared.GFPGAN.gfpgan import GFPGANer


def run_main(_input: str, _output: str) -> str:
	args = {
		'input': _input,
		'output': _output,
		'version': '1.3',
		'upscale': 2,
		'bg_upsampler': 'realesrgan',
		'bg_tile': 400,
		'suffix': None,
		'only_center_face': False,
		'aligned': False,
		'ext': 'auto',
		'weight': 0.5
	}

	# ------------------------ input & output ------------------------
	if args['input'].endswith('/'):
		args['input'] = args['input'][:-1]
	if os.path.isfile(args['input']):
		img_list = [args['input']]
	else:
		img_list = sorted(glob.glob(os.path.join(args['input'], '*')))

	os.makedirs(args['output'], exist_ok=True)

	# ------------------------ set up background upsampler ------------------------
	if args['bg_upsampler'] == 'realesrgan':
		if not torch.cuda.is_available():  # CPU
			import warnings
			warnings.warn('The unoptimized RealESRGAN is slow on CPU. We do not use it. '
						  'If you really want to use it, please modify the corresponding codes.')
			bg_upsampler = None
		else:
			from basicsr.archs.rrdbnet_arch import RRDBNet
			from realesrgan import RealESRGANer
			model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=2)
			bg_upsampler = RealESRGANer(
				scale=2,
				model_path='https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth',
				model=model,
				tile=args['bg_tile'],
				tile_pad=10,
				pre_pad=0,
				half=True)  # need to set False in CPU mode
	else:
		bg_upsampler = None

	# ------------------------ set up GFPGAN restorer ------------------------
	if args['version'] == '1':
		arch = 'original'
		channel_multiplier = 1
		model_name = 'GFPGANv1'
		url = 'https://github.com/TencentARC/GFPGAN/releases/download/v0.1.0/GFPGANv1.pth'
	elif args['version'] == '1.2':
		arch = 'clean'
		channel_multiplier = 2
		model_name = 'GFPGANCleanv1-NoCE-C2'
		url = 'https://github.com/TencentARC/GFPGAN/releases/download/v0.2.0/GFPGANCleanv1-NoCE-C2.pth'
	elif args['version'] == '1.3':
		arch = 'clean'
		channel_multiplier = 2
		model_name = 'GFPGANv1.3'
		url = 'https://github.com/TencentARC/GFPGAN/releases/download/v1.3.0/GFPGANv1.3.pth'
	elif args['version'] == '1.4':
		arch = 'clean'
		channel_multiplier = 2
		model_name = 'GFPGANv1.4'
		url = 'https://github.com/TencentARC/GFPGAN/releases/download/v1.3.0/GFPGANv1.4.pth'
	elif args['version'] == 'RestoreFormer':
		arch = 'RestoreFormer'
		channel_multiplier = 2
		model_name = 'RestoreFormer'
		url = 'https://github.com/TencentARC/GFPGAN/releases/download/v1.3.4/RestoreFormer.pth'
	else:
		raise ValueError(f'Wrong model version!')

	# determine model paths
	model_path = os.path.join('experiments/pretrained_models', model_name + '.pth')
	if not os.path.isfile(model_path):
		model_path = os.path.join('gfpgan/weights', model_name + '.pth')
	if not os.path.isfile(model_path):
		# download pre-trained models from url
		model_path = url

	restorer = GFPGANer(
		model_path=model_path,
		upscale=args['upscale'],
		arch=arch,
		channel_multiplier=channel_multiplier,
		bg_upsampler=bg_upsampler)

	# ------------------------ restore ------------------------
	for img_path in img_list:
		# read image
		img_name = os.path.basename(img_path)
		logger.debug(f'Processing {img_name} ...')
		basename, ext = os.path.splitext(img_name)
		input_img = cv2.imread(img_path, cv2.IMREAD_COLOR)

		# restore faces and background if necessary
		cropped_faces, restored_faces, restored_img = restorer.enhance(
			input_img,
			has_aligned=args['aligned'],
			only_center_face=args['only_center_face'],
			paste_back=True,
			weight=args['weight'])

		# save faces
		for idx, (cropped_face, restored_face) in enumerate(zip(cropped_faces, restored_faces)):
			# save cropped face
			save_crop_path = os.path.join(args['output'], 'cropped_faces', f'{basename}_{idx:02d}.png')
			imwrite(cropped_face, save_crop_path)
			# save restored face
			if args['suffix'] is not None:
				save_face_name = f'{basename}_{idx:02d}_{args["suffix"]}.png'
			else:
				save_face_name = f'{basename}_{idx:02d}.png'
			save_restore_path = os.path.join(args['output'], 'restored_faces', save_face_name)
			imwrite(restored_face, save_restore_path)
			# save comparison image
			cmp_img = np.concatenate((cropped_face, restored_face), axis=1)
			imwrite(cmp_img, os.path.join(args['output'], 'cmp', f'{basename}_{idx:02d}.png'))

		# save restored img
		if restored_img is not None:
			if args['ext'] == 'auto':
				extension = ext[1:]
			else:
				extension = args['ext']

			if args['suffix'] is not None:
				save_restore_path = os.path.join(args['output'], 'restored_imgs',
												 f'{basename}_{args["suffix"]}.{extension}')
			else:
				save_restore_path = os.path.join(args['output'], 'restored_imgs', f'{basename}.{extension}')
			imwrite(restored_img, save_restore_path)

	logger.debug(f'Results are in the [{args["output"]}] folder.')
	return args['output'] + '/restored_imgs/' + img_name
