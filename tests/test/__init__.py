import numpy


def handle(conf):
    # 获取参数
    gender = conf["gender1"]
    age = conf["age1"]


    aa = 0  # 建议给 aa 一个初始值，防止 if 不成立时后面报错

    if gender:
        aa = age + 100

    # print(aa)  # 在部署环境中，通常不建议在函数内部直接 print，除非为了调试

    return {'ret1': aa}


print(handle({'gender1':1,'age1':101}))