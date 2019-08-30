import pickle
from collections import defaultdict
import cpe


def parse_cpes(cpe_strs):
    my_cpes = []
    for cpe_str in cpe_strs:
        my_cpe_obj = cpe.CPE(cpe_str)
        my_cpes.append(my_cpe_obj)
    return my_cpes


def get_product_names(my_cpes):
    my_product_names = []
    product_names = {}
    for my_cpe in my_cpes:
        my_cpe_products = my_cpe.get_product()
        for my_product in my_cpe_products:
            if my_product not in product_names:
                my_product_names.append(my_product)
                product_names[my_product] = 1
            my_pn = my_product.replace("_", " ")
            if my_pn not in product_names:
                my_product_names.append(my_pn)
                product_names[my_pn] = 1
    return my_product_names


def get_vendor_names(my_cpes):
    my_vendor_names = []
    unique_vendor_names = {}
    for my_cpe in my_cpes:
        my_cpe_vendors = my_cpe.get_vendor()
        for my_vendor in my_cpe_vendors:
            if my_vendor not in unique_vendor_names:
                my_vendor_names.append(my_vendor)
                unique_vendor_names[my_vendor] = 1
            my_vn = my_vendor.replace("_", " ")
            if my_vn not in unique_vendor_names:
                my_vendor_names.append(my_vn)
                unique_vendor_names[my_vn] = 1
    return my_vendor_names




loadCVEs = True
if loadCVEs:
    cve_file = 'data/cve_desc.pickle'
    print("loading cve file:{}".format(cve_file))

    with open(cve_file, 'rb') as fp:
        cves = pickle.load(fp)




cpeToDesc = True
if cpeToDesc:
    print("Extract cpe product and vendor names.")
    summary_cpe_types = defaultdict(int)
    my_tokens = {}
    cve_cpe_pairs = {}
    cve_cpe_pnames = {}
    cve_cpe_vendors = {}
    cves_with_bad_cpes = []

    for cve_ind, cve_id in enumerate(cves):
        if cve_ind % 1000 == 0:
            print("{} cve processed".format(cve_ind))
            # break
        my_cve = cves[cve_id]
        try:
            my_cpe_objs = parse_cpes(my_cve['cpes'])
            # cve_cpe_pairs[cve_id] = my_cpe_objs
            cve_cpe_pnames[cve_id] = \
                get_product_names(my_cpe_objs)
            cve_cpe_vendors[cve_id] = \
                get_vendor_names(my_cpe_objs)
        except:
            cves_with_bad_cpes.append(cve_id)
