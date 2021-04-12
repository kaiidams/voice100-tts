import numpy as np

NORMPARAMS = {}

NORMPARAMS['kokoro_large-16000'] = np.array([ # mean, std
    [280.7665564234895, 130.06170199467167],
    [-5.870150198629327, 2.1144317227097096],
    [2.15874617426375, 1.0381763439050364],
    [0.4106754509761845, 0.4352808811309487],
    [0.7261360852529645, 0.4726384204265205],
    [0.21134753615249344, 0.3430762982655279],
    [0.39026360665728616, 0.2592549460503534],
    [0.02405501752108614, 0.2250123030306102],
    [0.1663026391304761, 0.20794432045679878],
    [-0.1123580421339392, 0.2022322938114597],
    [0.17585324245650255, 0.18800206824156376],
    [-0.14994181346876234, 0.23306706580658035],
    [0.19928631353791457, 0.18550216198889774],
    [-0.16693001338433155, 0.16485665739599767],
    [0.09752360902655469, 0.17015324056712489],
    [-0.047363666797188494, 0.15068735924672091],
    [0.1057092252203524, 0.149199242525545],
    [-0.09700145192406695, 0.1285107895499229],
    [0.091477115419671, 0.12387757732319883],
    [-0.12613852545198262, 0.11627936323889679],
    [0.06890710965275694, 0.1109305177308859],
    [-0.10324904900547216, 0.10688838686131903],
    [0.07156042885738721, 0.10606729459164585],
    [-0.10212232998948752, 0.10395081337437495],
    [0.051937746087681244, 0.10051798485803484],
    [-0.08699822070428007, 0.10115205514797229],
    [-3.051176135342112, 3.043502724255181],
], dtype=np.float64)

NORMPARAMS['kokoro_large-22050'] = np.array([ # mean, std
    [114.81156921386719, 35.89650344848633],
    [-6.300364017486572, 1.9752843379974365],
    [2.3838229179382324, 1.0255781412124634],
    [0.2400568276643753, 0.47543609142303467],
    [0.7894015312194824, 0.4659532904624939],
    [0.14851932227611542, 0.3271638751029968],
    [0.49938535690307617, 0.3133713901042938],
    [0.001201082719489932, 0.22512061893939972],
    [0.35634639859199524, 0.20609235763549805],
    [-0.15824787318706512, 0.212342768907547],
    [0.20235420763492584, 0.18757463991641998],
    [-0.13270379602909088, 0.17669892311096191],
    [0.134031280875206, 0.18306098878383636],
    [-0.10741252452135086, 0.21091803908348083],
    [0.1915627121925354, 0.16611851751804352],
    [-0.1937943696975708, 0.16210918128490448],
    [0.13450972735881805, 0.1521480232477188],
    [-0.08679914474487305, 0.13474704325199127],
    [0.13192981481552124, 0.12898457050323486],
    [-0.08783178776502609, 0.1301019936800003],
    [0.11155451834201813, 0.11323589086532593],
    [-0.08028512448072433, 0.11511655896902084],
    [0.06603807955980301, 0.10858893394470215],
    [-0.07223791629076004, 0.1062173843383789],
    [0.031667470932006836, 0.09967517107725143],
    [-0.05118199437856674, 0.09918227791786194],
    [0.03525080531835556, 0.09354250878095627],
    [-0.06541317701339722, 0.09846780449151993],
    [0.015907298773527145, 0.09387612342834473],
    [-0.027910321950912476, 0.0886090099811554],
    [0.0005205117631703615, 0.08596180379390717],
    [-0.015920307487249374, 0.08438711613416672],
    [-0.0109937135130167, 0.08391083031892776],
    [-0.0011818292550742626, 0.0810626819729805],
    [-0.017516763880848885, 0.08099629729986191],
    [0.030006693676114082, 0.08204881846904755],
    [-3.3009181022644043, 2.410651922225952],
    [-2.508110761642456, 1.2735965251922607],
  ], dtype=np.float32)

NORMPARAMS['cv_ja_kokoro_tiny-16000'] = np.array([
    [138.4299, 51.157955],
    [-6.2520027, 2.7529562],
    [1.8003883, 1.1860393],
    [0.10947099, 0.57256347],
    [0.6234376, 0.581813],
    [-0.09047311, 0.43370184],
    [0.2400902, 0.33497182],
    [-0.1336279, 0.3160605],
    [0.13538219, 0.27248532],
    [-0.16293816, 0.26333427],
    [0.13879842, 0.2450707],
    [-0.17094322, 0.24188843],
    [0.1680657, 0.21942285],
    [-0.17768836, 0.21589448],
    [0.15943107, 0.20297973],
    [-0.11965165, 0.18411867],
    [0.13924834, 0.18015544],
    [-0.1261882, 0.16407077],
    [0.117271036, 0.15318477],
    [-0.11959739, 0.15193588],
    [0.089462124, 0.14233512],
    [-0.101135835, 0.13570073],
    [0.08572928, 0.12846261],
    [-0.09829934, 0.12689443],
    [0.0839015, 0.122273795],
    [-0.08788245, 0.11788608],
    [-2.1679351, 2.7377384]
], dtype=np.float32)