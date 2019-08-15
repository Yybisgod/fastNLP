import os
from pathlib import Path
from urllib.parse import urlparse
import re
import requests
import tempfile
from tqdm import tqdm
import shutil
from requests import HTTPError

PRETRAINED_BERT_MODEL_DIR = {
    'en': 'bert-large-cased-wwm.zip',
    'en-large-cased-wwm': 'bert-large-cased-wwm.zip',
    'en-large-uncased-wwm': 'bert-large-uncased-wwm.zip',

    'en-large-uncased': 'bert-large-uncased.zip',
    'en-large-cased': 'bert-large-cased.zip',

    'en-base-uncased': 'bert-base-uncased.zip',
    'en-base-cased': 'bert-base-cased.zip',

    'en-base-cased-mrpc': 'bert-base-cased-finetuned-mrpc.zip',

    'en-base-multi-cased': 'bert-base-multilingual-cased.zip',
    'en-base-multi-uncased': 'bert-base-multilingual-uncased.zip',

    'cn': 'bert-chinese-wwm.zip',
    'cn-base': 'bert-base-chinese.zip',
    'cn-wwm': 'bert-chinese-wwm.zip',
}

PRETRAINED_ELMO_MODEL_DIR = {
    'en': 'elmo_en_Medium.tar.gz',
    'en-small': "elmo_en_Small.zip",
    'en-original-5.5b': 'elmo_en_Original_5.5B.zip',
    'en-original': 'elmo_en_Original.zip',
    'en-medium': 'elmo_en_Medium.zip'
}

PRETRAIN_STATIC_FILES = {
    'en': 'glove.840B.300d.tar.gz',

    'en-glove-6b-50d': 'glove.6B.50d.zip',
    'en-glove-6b-100d': 'glove.6B.100d.zip',
    'en-glove-6b-200d': 'glove.6B.200d.zip',
    'en-glove-6b-300d': 'glove.6B.300d.zip',
    'en-glove-42b-300d': 'glove.42B.300d.zip',
    'en-glove-840b-300d': 'glove.840B.300d.zip',
    'en-glove-twitter-27b-25d': 'glove.twitter.27B.25d.zip',
    'en-glove-twitter-27b-50d': 'glove.twitter.27B.50d.zip',
    'en-glove-twitter-27b-100d': 'glove.twitter.27B.100d.zip',
    'en-glove-twitter-27b-200d': 'glove.twitter.27B.200d.zip',

    'en-word2vec-300': "GoogleNews-vectors-negative300.zip",

    'en-fasttext-wiki': "wiki-news-300d-1M.vec.zip",
    'en-fasttext-crawl': "crawl-300d-2M.vec.zip",

    'cn': "tencent_cn.txt.zip",
    'cn-tencent': "tencent_cn.txt.zip",
    'cn-fasttext': "cc.zh.300.vec.gz",
    'cn-sgns-literature-word': 'sgns.literature.word.txt.zip',
}

DATASET_DIR = {
    'aclImdb': "imdb.zip",
    "yelp-review-full": "yelp_review_full.tar.gz",
    "yelp-review-polarity": "yelp_review_polarity.tar.gz",
    "mnli": "MNLI.zip",
    "snli": "SNLI.zip",
    "qnli": "QNLI.zip",
    "sst-2": "SST-2.zip",
    "sst": "SST.zip",
    "rte": "RTE.zip"
}


def cached_path(url_or_filename: str, cache_dir: str = None, name=None) -> Path:
    """
    给定一个url，尝试通过url中的解析出来的文件名字filename到{cache_dir}/{name}/{filename}下寻找这个文件，
        (1)如果cache_dir=None, 则cache_dir=~/.fastNLP/; 否则cache_dir=cache_dir
        (2)如果name=None, 则没有中间的{name}这一层结构；否者中间结构就为{name}

    如果有该文件，就直接返回路径
    如果没有该文件，则尝试用传入的url下载

    或者文件名(可以是具体的文件名，也可以是文件夹)，先在cache_dir下寻找该文件是否存在，如果不存在则去下载, 并
        将文件放入到cache_dir中.

    :param str url_or_filename: 文件的下载url或者文件名称。
    :param str cache_dir: 文件的缓存文件夹。如果为None，将使用"~/.fastNLP"这个默认路径
    :param str name: 中间一层的名称。如embedding, dataset
    :return:
    """
    if cache_dir is None:
        data_cache = Path(get_default_cache_path())
    else:
        data_cache = cache_dir

    if name:
        data_cache = os.path.join(data_cache, name)

    parsed = urlparse(url_or_filename)

    if parsed.scheme in ("http", "https"):
        # URL, so get it from the cache (downloading if necessary)
        return get_from_cache(url_or_filename, Path(data_cache))
    elif parsed.scheme == "" and Path(os.path.join(data_cache, url_or_filename)).exists():
        # File, and it exists.
        return Path(os.path.join(data_cache, url_or_filename))
    elif parsed.scheme == "":
        # File, but it doesn't exist.
        raise FileNotFoundError("file {} not found in {}.".format(url_or_filename, data_cache))
    else:
        # Something unknown
        raise ValueError(
            "unable to parse {} as a URL or as a local path".format(url_or_filename)
        )


def get_filepath(filepath):
    """
    如果filepath为文件夹，
        如果内含多个文件, 返回filepath
        如果只有一个文件, 返回filepath + filename

    如果filepath为文件
        返回filepath

    :param str filepath: 路径
    :return:
    """
    if os.path.isdir(filepath):
        files = os.listdir(filepath)
        if len(files) == 1:
            return os.path.join(filepath, files[0])
        else:
            return filepath
    elif os.path.isfile(filepath):
        return filepath
    else:
        raise FileNotFoundError(f"{filepath} is not a valid file or directory.")


def get_default_cache_path():
    """
    获取默认的fastNLP存放路径, 如果将FASTNLP_CACHE_PATH设置在了环境变量中，将使用环境变量的值，使得不用每个用户都去下载。

    :return: str
    """
    if 'FASTNLP_CACHE_DIR' in os.environ:
        fastnlp_cache_dir = os.environ.get('FASTNLP_CACHE_DIR')
        if os.path.isdir(fastnlp_cache_dir):
            return fastnlp_cache_dir
        else:
            raise NotADirectoryError(f"{os.environ['FASTNLP_CACHE_DIR']} is not a directory.")
    fastnlp_cache_dir = os.path.expanduser(os.path.join("~", ".fastNLP"))
    return fastnlp_cache_dir


def _get_base_url(name):
    """
    根据name返回下载的url地址。

    :param str name: 支持dataset和embedding两种
    :return:
    """
    # 返回的URL结尾必须是/
    environ_name = "FASTNLP_{}_URL".format(name.upper())

    if environ_name in os.environ:
        url = os.environ[environ_name]
        if url.endswith('/'):
            return url
        else:
            return url + '/'
    else:
        URLS = {
            'embedding': "http://dbcloud.irocn.cn:8989/api/public/dl/",
            "dataset": "http://dbcloud.irocn.cn:8989/api/public/dl/dataset/"
        }
        if name.lower() not in URLS:
            raise KeyError(f"{name} is not recognized.")
        return URLS[name.lower()]


def _get_embedding_url(type, name):
    """
    给定embedding类似和名称，返回下载url

    :param str type: 支持static, bert, elmo。即embedding的类型
    :param str name: embedding的名称, 例如en, cn, based等
    :return: str, 下载的url地址
    """
    PRETRAIN_MAP = {'elmo': PRETRAINED_ELMO_MODEL_DIR,
                    "bert": PRETRAINED_BERT_MODEL_DIR,
                    "static": PRETRAIN_STATIC_FILES}
    map = PRETRAIN_MAP.get(type, None)
    if map:
        filename = map.get(name, None)
        if filename:
            url = _get_base_url('embedding') + filename
            return url
        raise KeyError("There is no {}. Only supports {}.".format(name, list(map.keys())))
    else:
        raise KeyError(f"There is no {type}. Only supports bert, elmo, static")


def _get_dataset_url(name):
    """
    给定dataset的名称，返回下载url

    :param str name: 给定dataset的名称，比如imdb, sst-2等
    :return: str
    """
    filename = DATASET_DIR.get(name, None)
    if filename:
        url = _get_base_url('dataset') + filename
        return url
    else:
        raise KeyError(f"There is no {name}.")


def split_filename_suffix(filepath):
    """
    给定filepath返回对应的name和suffix. 如果后缀是多个点，仅支持.tar.gz类型
    :param filepath:
    :return: filename, suffix
    """
    filename = os.path.basename(filepath)
    if filename.endswith('.tar.gz'):
        return filename[:-7], '.tar.gz'
    return os.path.splitext(filename)


def get_from_cache(url: str, cache_dir: Path = None) -> Path:
    """
    尝试在cache_dir中寻找url定义的资源; 如果没有找到; 则从url下载并将结果放在cache_dir下，缓存的名称由url的结果推断而来。会将下载的
    文件解压，将解压后的文件全部放在cache_dir文件夹中。

    如果从url中下载的资源解压后有多个文件，则返回目录的路径; 如果只有一个资源文件，则返回具体的路径。
    """
    cache_dir.mkdir(parents=True, exist_ok=True)

    filename = re.sub(r".+/", "", url)
    dir_name, suffix = split_filename_suffix(filename)

    # 寻找与它名字匹配的内容, 而不关心后缀
    match_dir_name = match_file(dir_name, cache_dir)
    if match_dir_name:
        dir_name = match_dir_name
    cache_path = cache_dir / dir_name

    # get cache path to put the file
    if cache_path.exists():
        return get_filepath(cache_path)

    # make HEAD request to check ETag TODO ETag可以用来判断资源是否已经更新了，之后需要加上
    # response = requests.head(url, headers={"User-Agent": "fastNLP"})
    # if response.status_code != 200:
    #     raise IOError(
    #         f"HEAD request failed for url {url} with status code {response.status_code}."
    #     )

    # add ETag to filename if it exists
    # etag = response.headers.get("ETag")

    if not cache_path.exists():
        # Download to temporary file, then copy to cache dir once finished.
        # Otherwise you get corrupt cache entries if the download gets interrupted.
        fd, temp_filename = tempfile.mkstemp()
        print("%s not found in cache, downloading to %s" % (url, temp_filename))

        # GET file object
        req = requests.get(url, stream=True, headers={"User-Agent": "fastNLP"})
        if req.status_code == 200:
            content_length = req.headers.get("Content-Length")
            total = int(content_length) if content_length is not None else None
            progress = tqdm(unit="B", total=total, unit_scale=1)
            with open(temp_filename, "wb") as temp_file:
                for chunk in req.iter_content(chunk_size=1024 * 16):
                    if chunk:  # filter out keep-alive new chunks
                        progress.update(len(chunk))
                        temp_file.write(chunk)
            progress.close()
            print(f"Finish download from {url}.")

            # 开始解压
            delete_temp_dir = None
            if suffix in ('.zip', '.tar.gz'):
                uncompress_temp_dir = tempfile.mkdtemp()
                delete_temp_dir = uncompress_temp_dir
                print(f"Start to uncompress file to {uncompress_temp_dir}")
                if suffix == '.zip':
                    unzip_file(Path(temp_filename), Path(uncompress_temp_dir))
                else:
                    untar_gz_file(Path(temp_filename), Path(uncompress_temp_dir))
                filenames = os.listdir(uncompress_temp_dir)
                if len(filenames) == 1:
                    if os.path.isdir(os.path.join(uncompress_temp_dir, filenames[0])):
                        uncompress_temp_dir = os.path.join(uncompress_temp_dir, filenames[0])

                cache_path.mkdir(parents=True, exist_ok=True)
                print("Finish un-compressing file.")
            else:
                uncompress_temp_dir = temp_filename
                cache_path = str(cache_path) + suffix
            success = False
            try:
                # 复制到指定的位置
                print(f"Copy file to {cache_path}")
                if os.path.isdir(uncompress_temp_dir):
                    for filename in os.listdir(uncompress_temp_dir):
                        if os.path.isdir(os.path.join(uncompress_temp_dir, filename)):
                            shutil.copytree(os.path.join(uncompress_temp_dir, filename), cache_path / filename)
                        else:
                            shutil.copyfile(os.path.join(uncompress_temp_dir, filename), cache_path / filename)
                else:
                    shutil.copyfile(uncompress_temp_dir, cache_path)
                success = True
            except Exception as e:
                print(e)
                raise e
            finally:
                if not success:
                    if cache_path.exists():
                        if cache_path.is_file():
                            os.remove(cache_path)
                        else:
                            shutil.rmtree(cache_path)
                if delete_temp_dir:
                    shutil.rmtree(delete_temp_dir)
                os.close(fd)
                os.remove(temp_filename)
            return get_filepath(cache_path)
        else:
            raise HTTPError(f"Fail to download from {url}.")


def unzip_file(file: Path, to: Path):
    # unpack and write out in CoNLL column-like format
    from zipfile import ZipFile

    with ZipFile(file, "r") as zipObj:
        # Extract all the contents of zip file in current directory
        zipObj.extractall(to)


def untar_gz_file(file: Path, to: Path):
    import tarfile

    with tarfile.open(file, 'r:gz') as tar:
        tar.extractall(to)


def match_file(dir_name: str, cache_dir: Path) -> str:
    """
    匹配的原则是，在cache_dir下的文件: (1) 与dir_name完全一致; (2) 除了后缀以外和dir_name完全一致。
    如果找到了两个匹配的结果将报错. 如果找到了则返回匹配的文件的名称; 没有找到返回空字符串

    :param dir_name: 需要匹配的名称
    :param cache_dir: 在该目录下找匹配dir_name是否存在
    :return: str
    """
    files = os.listdir(cache_dir)
    matched_filenames = []
    for file_name in files:
        if re.match(dir_name + '$', file_name) or re.match(dir_name + '\\..*', file_name):
            matched_filenames.append(file_name)
    if len(matched_filenames) == 0:
        return ''
    elif len(matched_filenames) == 1:
        return matched_filenames[-1]
    else:
        raise RuntimeError(f"Duplicate matched files:{matched_filenames}, this should be caused by a bug.")
