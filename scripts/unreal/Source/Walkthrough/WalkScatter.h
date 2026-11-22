// Instanced scatter of one mesh (trees, grass clumps, parked cars). import_manifest.py spawns one actor per
// prototype mesh and calls SetInstances; the instances are saved with the level.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "WalkScatter.generated.h"

class UHierarchicalInstancedStaticMeshComponent;
class UStaticMesh;

UCLASS()
class WALKTHROUGH_API AWalkScatter : public AActor
{
	GENERATED_BODY()

public:
	AWalkScatter();

	/** Replace all instances. Transforms in world space (cm). CullStart/CullEnd fade far instances (cm).
	 *  Grass: 3000/4500 and no shadows. Trees: 45000/60000 with shadows. The materials need
	 *  "Used with Instanced Static Meshes", or they draw with the grey default material. */
	UFUNCTION(BlueprintCallable, Category = "Walkthrough")
	void SetInstances(UStaticMesh* Mesh, const TArray<FTransform>& Transforms, float CullStart = 3500.f,
		float CullEnd = 5000.f, bool bShadows = false);

	UPROPERTY(VisibleAnywhere, Category = "Walkthrough")
	TObjectPtr<UHierarchicalInstancedStaticMeshComponent> Instances;
};
