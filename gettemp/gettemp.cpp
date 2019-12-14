#include <sensors/sensors.h>
#include <string>
#include <sstream>
#include <iostream>


using namespace std;

bool printtemps(string chipname, string featurename) {
    sensors_feature const *feat;
    int c = 0;
    sensors_chip_name const * cn;
    while ((cn = sensors_get_detected_chips(0, &c)) != 0) {
        if (chipname == cn->prefix) {
            int f = 0;
            while ((feat = sensors_get_features(cn, &f)) != 0) {
                if (featurename == feat->name) {
                    sensors_subfeature const *subf;
                    int s = 0;
                    while ((subf = sensors_get_all_subfeatures(cn, feat, &s)) != 0) {
                        if ((featurename + "_input") == subf->name) {
                            double val;
                            if (subf->flags & SENSORS_MODE_R) {
                                int rc = sensors_get_value(cn, subf->number, &val);
                                if (rc < 0) {
                                    std::cerr << "err: " << rc << endl;
                                    return false;
                                } else {
                                    std::cout << val << endl;
                                    return true;
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    return false;
}

int main(int argc, char** argv) {
    string chip, feature;
    sensors_init(NULL);
    for (int i=1; i<argc; ++i) {
        string arg(argv[i]);
        size_t dot = arg.find(".");
        if (dot == string::npos) {
            cerr << "gettemp error: No dot in arg " << arg << endl;
            return 1;
        }
        printtemps(arg.substr(0, dot), arg.substr(dot+1));
    }
    sensors_cleanup();

}
