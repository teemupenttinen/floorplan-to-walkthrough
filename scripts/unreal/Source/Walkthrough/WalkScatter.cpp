#include "WalkScatter.h"

#include "Components/HierarchicalInstancedStaticMeshComponent.h"

AWalkScatter::AWalkScatter()
{
	PrimaryActorTick.bCanEverTick = false;
	Instances = CreateDefaultSubobject<UHierarchicalInstancedStaticMeshComponent>(TEXT("Instances"));
	RootComponent = Instances;
	Instances->SetMobility(EComponentMobility::Static);
	// Nobody walks into a grass clump or a distant tree: no collision keeps the physics scene small.
	Instances->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Instances->bAffectDistanceFieldLighting = false;
}

void AWalkScatter::SetInstances(UStaticMesh* Mesh, const TArray<FTransform>& Transforms, float CullStart, float CullEnd, bool bShadows)
{
	Instances->ClearInstances();
	Instances->SetStaticMesh(Mesh);
	Instances->SetCullDistances(int32(CullStart), int32(CullEnd));
	Instances->SetCastShadow(bShadows);
	Instances->AddInstances(Transforms, false, true);
	Instances->BuildTreeIfOutdated(false, true);
	Modify();
}
