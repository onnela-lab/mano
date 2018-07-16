from setuptools import setup, find_packages

requires = [
    'requests', 
    'lxml',
    'vcrpy',
    'pytest'
]

setup(name='mano',
      description='Mano - API for Beiwe Research Platform',
      author='Neuroinformatics Research Group',
      author_email='info@neuroinfo.org',
      packages=find_packages(),
      url='http://neuroinformatics.harvard.edu/',
      install_requires=requires
)
