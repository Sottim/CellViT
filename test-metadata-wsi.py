import openslide
slide = openslide.OpenSlide('/home/KutumLabGPU/Documents/santosh/CellViT/example/20190610_111_551-14_4069-15-A_Biopsy_ER_HnE_40X_pyramid.tif')
properties = slide.properties
print(properties)

print(f"Number of levels in the WSI: {slide.level_count}")